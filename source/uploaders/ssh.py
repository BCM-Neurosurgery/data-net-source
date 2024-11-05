import os
import sys
import json
import pathlib
import logging
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import paramiko

from paramiko import SSHClient
from scp import SCPClient

from source.uploaders.base import BaseUploader

# Suppress verbosity of paramiko logger
logging.getLogger("paramiko").setLevel(logging.WARNING)


class SCPUploaderMixin(BaseUploader):
    """
    This uploader expects a target location of the form of a dict as below
    {
      "ssh-config": {dict of kwargs passed to paramiko.SSHClient},
      "path": /base/path/on/remote"
    }
    """

    uploader_name = 'SCPUploader'

    def get_ssh_transport(self):
        # Set up the ssh client and associated scp transport
        self.info('Connecting to remote host...')
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(**self.target_location['ssh-config'])
        scp = SCPClient(ssh.get_transport())
        self.info('Established connection')
        return ssh, scp

    def upload(self, ready):

        errors = ready['failure']
        successes = []
        all_rates = []

        remote_target = self.target_location['path']
        ssh, scp = self.get_ssh_transport()

        for filename in ready['to upload']:
            destination = 'Failed to determine!'
            try:
                self.info(f'Uploading {filename}')
                rel_filepath = os.path.relpath(
                    filename, start=self.middle_location['path']
                )

                # Make sure the destination folder exists using ssh. We assume a *nix destination
                # This solution is a bit hacky, likely executes a lot more commands than necessary
                new_rel_path = self.rebuild_filepath(rel_filepath)
                folder_path = pathlib.Path(remote_target, os.path.dirname(new_rel_path))
                outputs = ssh.exec_command(f'mkdir -p {folder_path.as_posix()}')

                # Actually do the file copy
                destination = pathlib.Path(remote_target, new_rel_path)
                self.info(f'  Moving to {destination}')
                size = os.path.getsize(filename) / 1024 ** 2  # File size in MB
                rate = self.time_upload(size, scp.put, filename, destination.as_posix())
                self.info(f'  Upload complete. ({np.round(size, 2)} MB at {np.round(rate, 2)} MB/s)')
                if size > 1.0:
                    all_rates.append(rate)
            except Exception as e:
                error_dict = {
                    'type': 'upload failure',
                    'location': 'SCPUploaderMixin.upload',
                    'filename': str(filename),
                    'destination': str(destination),
                    'error': str(e),
                    'trace': traceback.format_exception(*sys.exc_info())
                }
                errors.append(error_dict)
                self.warning('An upload failed!')
                self.warning(json.dumps(error_dict, indent=2))
            else:
                successes.append({
                    'type': 'upload success',
                    'filename': filename,
                    'destination': destination,
                    'transfer rate': rate
                })

        # Make sure we close the transports
        scp.close()
        ssh.close()
        self.info(f'Average transfer rate {round(np.nanmean(all_rates), 2)} MB/s')

        return {
            'success': successes, 'failure': errors
        }


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

    def connect(self):
        """Open a paramiko SFTP connection to the remote server"""
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(**self.target_location['sftp'])
        sftp = ssh.open_sftp()
        return sftp

    def upload(self, ready):

        success = []
        errors = [*ready['failure']]

        with self.connect() as sftp:

            for file in ready['to do']:

                try:

                    sftp.makedirs(Path(self.remote_dirpath(file)).as_posix(), exist_ok=True)
                    file_size = os.path.getsize(file)
                    self.info(f'Moving file: {file}')
                    upload_rate = self.time_upload(
                        file_size,
                        sftp.put,
                        file, Path(self.remote_filepath(file)).as_posix()
                    )

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
                    self.info(f'  Upload complete. ({round(file_size, 2)} MB at {round(upload_rate, 2)} MB/s)')
                    success.append({
                        'type': 'upload success',
                        'filename': file,
                        'destination': self.remote_filepath(file),
                        'transfer rate': upload_rate
                    })
        return {'success': success, 'failure': errors}
