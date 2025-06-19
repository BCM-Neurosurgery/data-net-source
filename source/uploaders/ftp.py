import os
import sys
import ftplib
import pathlib
import traceback
from ftputil import FTPHost
from ftputil.error import FTPError
from source.uploaders.base import RemoteFilesystemUploader


class FTPUploader(RemoteFilesystemUploader):
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

    def make_connection(self):
        """
        Establish a connection to the remote filesystem
        Connection reference should be stored as instance variables
        """
        ftp_backend = ftplib.FTP_TLS if self.use_tls else ftplib.FTP
        self.ftp = FTPHost(**self.target_location['ftp'], session_factory=ftp_backend)

    def close_connection(self):
        """"""
        self.ftp.close()

    def check_exists(self, target_file):
        """Check if the file exists by trying to retrieve it's size. Error indicates file does not exist"""
        try:
            size = self.ftp.stat(target_file)
        except FTPError as e:
            exists = False
        else:
            exists = True
        return exists

    def make_folders(self, target_directory):
        self.ftp.makedirs(pathlib.Path(target_directory).as_posix(), exist_ok=True)

    def do_move(self, filename, destination):
        return self.time_upload(self.ftp.upload, filename, destination.as_posix())



