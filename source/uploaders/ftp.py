import os
import sys
import ftplib
import pathlib
import traceback
from ftputil import FTPHost
from source.uploaders.base import BaseUploader


class FTPUploader(BaseUploader):
    """
    Uploader that users FTP (with TLS by default) to transfer files to an FTP server
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


