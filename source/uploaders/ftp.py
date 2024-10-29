import os
import pathlib

from ftplib import FTP
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
            "password": ""
        }
    }

    def connect_to_ftp(self):
        ftp_config = self.target_location['ftp']
        ftp = FTP(**ftp_config)
        return ftp

    def build_filepath(self, ftp, current, continued):
        """
        Recursively step down to the desired path creating directories as necessary

        """
        try:
            ftp.cwd(current)
        except FileNotFoundError:
            ftp.mkd(current)
            ftp.cwd(current)

        if continued:
            split_path = pathlib.Path(continued).parts
            new_current = os.path.join(current, split_path[0])
            new_continued = os.path.join(*split_path[1:])
            return self.build_filepath(ftp, new_current, new_continued)
        else:
            return current

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

        with self.connect_to_ftp() as ftp:

            remote_base = self.target_location['path']
            local_base = self.middle_location['path']

            for file in ready['to_do']:

                relative_path = pathlib.Path(os.path.relpath(local_base, file))
                self.build_filepath(ftp, remote_base, relative_path)

                filename = pathlib.Path(file).parts[-1]

                with open(os.path.join(local_base, relative_path), 'rb') as fp:
                    ftp.storbinary(f'STOR {filename}', fp)









