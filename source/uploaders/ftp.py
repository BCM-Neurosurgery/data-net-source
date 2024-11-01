import os
import sys
import ftplib
import pathlib
import paramiko
import traceback

from ftputil import FTPHost
from source.uploaders.base import BaseUploader


class FTPUploader(BaseUploader):
    """

    """

    uploader_name = "FTPUploader"
    middle_location = {"path": ""}
    target_location = {
        "path": "",
        "ftp": {
            "host": "",
            "user": "",
            "passwd": ""
        }
    }

    use_tls = True

    def upload(self, ready):
        """
        Upload a file to the remote server using FTP

        Steps:
            - Establish an FTP connection and authenticate
            - Ensure the target base dir exists and CD to it
            - For each file:
               - Ensure the target file directory exists (may need to recursively .mkd() folders)
               - Use .storbinary(...) to move the file to the remote location
               - Return back to the base dir

        :param ready:
        :return:
        """

        errors = ready['failure']
        success = []

        ftp_backend = ftplib.FTP_TLS if self.use_tls else ftplib.FTP

        with FTPHost(**self.target_location['ftp'], session_factory=ftp_backend) as ftp:

            remote_base = self.target_location['path']
            local_base = self.middle_location['path']

            for file in ready['to upload']:

                try:
                    relative_path = os.path.relpath(file, local_base)
                    remote_path = os.path.join(remote_base, relative_path)

                    remote_dir = os.path.dirname(remote_path)
                    ftp.makedirs(pathlib.Path(remote_dir).as_posix(), exist_ok=True)

                    file_size = os.path.getsize(file)
                    self.info(f'  Moving to {remote_path}')
                    upload_rate = self.time_upload(
                        file_size,
                        ftp.upload,
                        pathlib.Path(file).as_posix(),
                        pathlib.Path(remote_path).as_posix()
                    )
                except Exception as e:
                    self.error(e)
                    error_dict = {
                        'type': 'upload failure',
                        'location': self.uploader_name,
                        'filename': str(file),
                        'destination': str(remote_path),
                        'error': str(e),
                        'trace': traceback.format_exception(*sys.exc_info())
                    }
                    errors.append(error_dict)
                else:
                    self.info(f'  Upload complete. ({round(file_size, 2)} MB at {round(upload_rate, 2)} MB/s)')
                    success.append({
                        'type': 'upload success',
                        'filename': file,
                        'destination': remote_path,
                        'transfer rate': upload_rate
                    })
        return {'success': success, 'failure': errors}


class SFTPUploader(BaseUploader):
    """
    Use the SFTP protocol to transfer files to a remote server
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

    def get_connection(self):
        """Open a paramiko SFTP connection to the remote server"""
        sftp_config = self.target_location['sftp']
        transport = paramiko.Transport((sftp_config['host'], sftp_config['port']))
        transport.connect(None, sftp_config['user'], sftp_config['password'])
        sftp = paramiko.SFTPClient.from_transport(transport)
        return sftp

    def upload_file(self, ready):

        success = []
        errors = [*ready['failures']]

        with self.connect() as sftp:

            for file in ready['to do']:

                try:

                    sftp.makedirs(self.remote_dirpath(file), exist_ok=True)

                    self.info(f'Moving file: {file}')
                    sftp.put(file, self.remote_filepath(file))

                except Exception as e:
                    self.error(f'Failed when moving {file} with error {e}')
                    errors.append({
                        'type': 'upload failure',
                        'location': self.uploader_name,
                        'filename': str(file),
                        'destination': str(self.remote_filepath(file)),
                        'error': str(e),
                        'trace': traceback.format_exception(*sys.exc_info())
                    })
                else:
                    self.info('Move complete')
                    success.append({
                        'type': 'upload success',
                        'filename': file,
                        'destination': self.remote_filepath(file),
                        'transfer rate': float('nan')
                    })
        return {'success': success, 'failure': errors}

