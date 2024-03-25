import json
import os
import shutil
import sys
import pathlib
import numpy as np
from source.uploaders.base import BaseUploader


class BucketUploaderMixin(BaseUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """

    uploader_name = "BucketUploaderMixin"

    def upload(self, ready):
        raise NotImplementedError


class CopyUploaderMixin(BaseUploader):

    uploader_name = "CopyUploaderMixin"

    def upload(self, ready):

        errors = ready['failure']
        successes = []
        all_rates = []

        for filename in ready['to upload']:
            destination = 'Failed to determine!'
            try:
                rel_filepath = os.path.relpath(filename, start=self.source_location)

                # Make sure the destination folder exists
                folder_path = os.path.join(self.target_location, os.path.dirname(rel_filepath))
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                # Perform the file copy
                destination = os.path.join(self.target_location, rel_filepath)
                self.info(f'Copying to {destination}', )
                size = os.path.getsize(filename) / 1024 ** 2  # File size in MB
                rate = self.time_upload(size, shutil.copy, filename, destination)
                self.info(f'  Done. ({np.round(size, 2)} MB at {np.round(rate, 2)} MB/s)')

                if size > 1.0:
                    all_rates.append(rate)

            except Exception as e:
                error_dict = {
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': filename,
                    'destination': destination,
                    'error': str(e),
                    'trace': sys.exc_info()
                }
                errors.append(error_dict)
                self.warning('An upload failed!')
                self.warning(json.dumps(error_dict, indent=2))
            else:
                successes.append({
                    'type': 'upload success',
                    'filename': filename,
                    'destination': destination,
                })

        self.info(f'Average transfer rate {round(np.nanmean(all_rates), 2)} MB/s')
        return {
            'success': successes, 'failure': errors
        }


class SCPUploaderMixin:
    """
    This uploader expects a target location of the form of a dict as below
    {
      "ssh-config": {dict of kwargs passed to paramiko.SSHClient},
      "path": /base/path/on/remote"
    }
    """

    uploader_name = 'SCPUploader'

    def get_ssh_transport(self):
        # Local imports used only here
        from paramiko import SSHClient
        from scp import SCPClient
        # Set up the ssh client and associated scp transport
        self.info('Connecting to remote host...')
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(**self.target_location['ssh-config'])
        scp = SCPClient(ssh.get_transport())
        self.info('Established connection')
        return scp

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
                rel_filepath = os.path.relpath(filename, start=self.source_location)

                # Make sure the destination folder exists using ssh. We assume a *nix destination
                # This solution is a bit hacky, likely executes a lot more commands than necessary
                folder_path = pathlib.Path(remote_target, os.path.dirname(rel_filepath))
                outputs = ssh.exec_command(f'mkdir -p {folder_path.as_posix()}')

                # Actually do the file copy
                destination = pathlib.Path(remote_target, rel_filepath)
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
                    'filename': filename,
                    'destination': destination,
                    'error': str(e),
                    'trace': sys.exc_info()
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