import errno
import logging
import os
import shlex
import stat
import uuid
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
        try:
            self.sftp = self.ssh.open_sftp()
            self.scp = SCPClient(self.ssh.get_transport())
        except Exception:
            self.ssh.close()
            raise
        self.info('Established connection')

    def close_connection(self):
        try:
            self.scp.close()
        finally:
            try:
                self.sftp.close()
            finally:
                self.ssh.close()

    def _run_remote_command(self, command):
        """Run a small remote filesystem command and propagate errors to upload()."""
        stdin, stdout, stderr = self.ssh.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise ChildProcessError(f'Remote command failed ({exit_status}): {command}\n{error}')
        return output

    def remote_size(self, target_file):
        """Return the byte size of a regular remote file, or None if absent."""
        try:
            attributes = self.sftp.stat(target_file.as_posix())
        except OSError as error:
            if error.errno == errno.ENOENT:
                return None
            raise
        if not stat.S_ISREG(attributes.st_mode):
            raise ValueError(f'Destination is not a regular file: {target_file}')
        return attributes.st_size

    def check_exists(self, target_file):
        return self.remote_size(target_file) is not None

    def check_complete(self, filename, destination):
        """Only skip existing files whose size matches the local source."""
        remote_size = self.remote_size(destination)
        if remote_size is None:
            return False
        source_size = os.path.getsize(filename)
        if remote_size != source_size:
            raise ValueError(
                f'Destination size mismatch for {destination}: '
                f'source={source_size} bytes, destination={remote_size} bytes. '
                f'Repair the destination or enable allow-overwrite to replace it.'
            )
        return True

    def make_folders(self, target_directory):
        self._run_remote_command(f'mkdir -p -- {shlex.quote(target_directory.as_posix())}')
        self.info('Folders successfully created on server')

    def do_move(self, filename, destination):
        """Validate a temporary SCP upload before publishing it with SFTP rename."""
        source_stat = os.stat(filename)
        temporary = destination.parent / f'.upload-{uuid.uuid4().hex}.part'
        try:
            timing = self.time_upload(self.scp.put, filename, temporary.as_posix())
            remote_size = self.remote_size(temporary)
            if remote_size != source_stat.st_size:
                raise ValueError(
                    f'Uploaded size mismatch for {destination}: '
                    f'source={source_stat.st_size} bytes, uploaded={remote_size} bytes'
                )
            current_stat = os.stat(filename)
            if (current_stat.st_size, current_stat.st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns):
                raise ValueError(f'Source changed during upload: {filename}')

            if self.target_location.get('allow-overwrite', False):
                self.sftp.posix_rename(temporary.as_posix(), destination.as_posix())
            else:
                self.sftp.rename(temporary.as_posix(), destination.as_posix())
            return timing
        except Exception:
            try:
                self.sftp.remove(temporary.as_posix())
            except FileNotFoundError:
                pass
            except Exception as cleanup_error:
                self.warning(f'Could not remove temporary upload {temporary}: {cleanup_error}')
            raise


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
