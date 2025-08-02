# source/uploaders/ssh.py

import os
from datetime import datetime
from pathlib import Path # Import the Path object for type checking
from .base import RemoteFilesystemUploader # Inherits from the remote uploader base
import logging
import paramiko # The library for SSH and SCP

class SCPUploaderMixin(RemoteFilesystemUploader):
    """
    An Uploader mixin that securely sends files to a remote server using SCP.
    It preserves the relative directory structure from the temporary folder.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sftp = None
        self.ssh = None

    @property
    def uploader_name(self):
        """
        Provides a user-friendly name for this uploader.
        """
        return "SCPUploader"

    def make_connection(self):
        """
        Establishes an SSH connection to the remote server using either a private key or a password.
        """
        hostname = self.target_location.get('hostname')
        username = self.target_location.get('username')
        # Look for a password in the [parser.init.target] section of the config.
        password = self.target_location.get('password', None)
        # Look for a key_filepath in the [parser.settings] section of the config.
        key_filepath = getattr(self, 'key_filepath', None)

        if not hostname or not username:
            raise ValueError("Hostname and username are required for SCP uploader.")

        self.info(f"Connecting to {username}@{hostname} via SSH...")
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Paramiko will automatically try the key first, then fall back to the password if provided.
            self.ssh.connect(
                hostname=hostname,
                username=username,
                password=password,
                key_filename=key_filepath
            )
            self.sftp = self.ssh.open_sftp()
            self.info("SSH connection established.")
        except Exception as e:
            self.error(f"Failed to establish SSH connection: {e}")
            raise e

    def close_connection(self):
        """
        Closes the SFTP and SSH connections.
        """
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()
        self.info("SSH connection closed.")

    def check_exists(self, target_file):
        """
        Checks if a file already exists on the remote server.
        """
        try:
            # The target_file from the base class is a Path object, convert to string for SFTP.
            self.sftp.stat(str(target_file))
            return True
        except FileNotFoundError:
            return False

    def make_folders(self, target_directory):
        """
        Recursively creates a directory structure on the remote server.
        """
        # The target_directory from the base class is a Path object, convert to string.
        target_dir_str = str(target_directory).replace('\\', '/')
        if target_dir_str == '/':
            # The root directory always exists.
            return
        try:
            self.sftp.stat(target_dir_str)
        except FileNotFoundError:
            # The directory doesn't exist, so we create its parent first, then this one.
            self.make_folders(os.path.dirname(target_dir_str))
            self.info(f"Creating remote directory: {target_dir_str}")
            self.sftp.mkdir(target_dir_str)

    def do_move(self, filename, destination):
        """
        Performs the actual file transfer using SCP (via SFTP put).
        """
        # The destination from the base class is a Path object, convert to string.
        destination_str = str(destination).replace('\\', '/')
        self.sftp.put(filename, destination_str)

    def upload(self, ready: dict) -> dict:
        """
        Wrapper around the parent upload method to fix a JSON serialization issue.
        """
        # Call the parent's upload method which handles the connection and the main upload loop.
        results = super().upload(ready)

        # The parent class's upload method returns Path objects in the success list,
        # which are not JSON serializable. We must convert them to strings here.
        for success_record in results.get('success', []):
            if 'destination' in success_record and isinstance(success_record['destination'], Path):
                # Convert the Path object to a POSIX-style string (using forward slashes).
                success_record['destination'] = success_record['destination'].as_posix()

        return results
