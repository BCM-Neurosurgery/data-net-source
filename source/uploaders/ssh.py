import logging
from pathlib import Path

from paramiko import SSHClient
from scp import SCPClient

from source.uploaders.base import RemoteFilesystemUploader

# Suppress verbosity of paramiko logger
logging.getLogger("paramiko").setLevel(logging.WARNING)


class SCPUploaderMixin(RemoteFilesystemUploader):
    """
    This uploader expects a target location of the form of a dict as below
    {
      "ssh-config": {dict of kwargs passed to paramiko.SSHClient},
      "path": /base/path/on/remote"
    }
    """

    uploader_name = 'SCPUploader'

    def make_connection(self):
        """Set up the ssh client and associated scp transport"""
        self.info('Connecting to remote host...')
        self.ssh = SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.connect(**self.target_location['ssh-config'])
        self.scp = SCPClient(self.ssh.get_transport())
        self.info('Established connection')

    def close_connection(self):
        self.scp.close()
        self.ssh.close()

    def check_exists(self, target_file):
        stdin, stdout, stderr = self.ssh.exec_command(f'test -e {target_file} && echo exists')
        response = stdout.read()
        self.debug(f'stdout: {response}')
        return response == 'exists'

    def make_folders(self, target_directory):
        self.ssh.exec_command(f'mkdir -p {target_directory.as_posix()}')

    def do_move(self, filename, destination):
        return self.time_upload(self.scp.put, filename, destination.as_posix())


class SFTPUploader(RemoteFilesystemUploader):
    """
    Use the SFTP protocol to transfer files to a remote server. Assume posix destination
    """

    uploader_name = "SFTPUploader"
    middle_location = {"path": ""}
    target_location = {
        "path": "",
        "sftp": {
            "host": "",
            "port": 22,
            "user": "",
            "password": ""
        }
    }

    def make_connection(self):
        """Open a paramiko SFTP connection to the remote server"""
        self.ssh = SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.connect(**self.target_location['sftp'])
        self.sftp = self.ssh.open_sftp()

    def check_exists(self, target_file):
        return self.ssh.exec_command(f'test -f {target_file}')

    def make_folders(self, target_directory):
        self.sftp.makedirs(Path(target_directory).as_posix(), exist_ok=True)

    def do_move(self, filename, destination):
        return self.time_upload(self.sftp.put, filename, destination.as_posix())

    def close_connection(self):
        self.sftp.close()
        self.ssh.close()
