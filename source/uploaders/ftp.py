import os
import pathlib

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

        with FTPHost(**self.target_location['ftp']) as ftp:

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
                    self.info(f'  Upload complete. ({round(file_size, 2)} MB at {round(upload_rate, 2)} MB/s)')
                except Exception as e:
                    print(e)
                else:
                    print(f'success')










