import os
import shutil
import sys
import pathlib
import numpy as np
from datetime import datetime
from source.uploaders.base import BaseUploader


class BucketUploaderMixin(BaseUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """

    uploader_name = "BucketUploaderMixin"

    def upload(self, ready):
        raise NotImplementedError


class CopyUploaderMixin(BaseUploader):

    uploader_name = "SimpleCopyMixin"

    def upload(self, ready):

        errors = ready['failure']
        successes = []

        for filename in ready['to upload']:
            destination = 'Failed to determine!'
            try:
                rel_filepath = os.path.relpath(filename, start=self.source_location)

                # Make sure the destination folder exists
                folder_path = os.path.join(self.target_location, os.path.dirname(rel_filepath))
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                destination = os.path.join(self.target_location, rel_filepath)
                print(f'  Copying to {destination}')
                rate = self.time_upload(shutil.copy, filename, destination)
                print(f'  Done. ({rate} MB/s)')
            except Exception as e:
                errors.append({
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': filename,
                    'destination': destination,
                    'error': str(e),
                    'trace': sys.exc_info()
                })
            else:
                successes.append({
                    'type': 'upload success',
                    'filename': filename,
                    'destination': destination,
                })

        return {
            'success': successes, 'failure': errors
        }


class SCPUploaderMixin:
    """
    This uploader expects a target location of the form of a dict as below
    {
      "ssh-config": {dict passed to paramiko.SSHClient},
      "path": /base/path/on/remote"
    }
    """

    uploader_name = 'SCPUploader'

    def get_ssh_transport(self):
        # Local imports used only here
        from paramiko import SSHClient
        from scp import SCPClient
        # Set up the ssh client and associated scp transport
        print('Connecting to remote host...')
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(**self.target_location['ssh-config'])
        scp = SCPClient(ssh.get_transport())
        print('Established connection')
        return scp

    def upload(self, ready):

        errors = ready['failure']
        successes = []
        remote_target = self.target_location['path']
        all_rates = []

        ssh, scp = self.get_ssh_transport()

        for filename in ready['to upload']:
            destination = 'Failed to determine!'
            try:
                print(f'  Uploading {filename}')
                rel_filepath = os.path.relpath(filename, start=self.source_location)

                # Make sure the destination folder exists using ssh. We assume a *nix destination
                # This solution is a bit hacky, likely executes a lot more commands than necessary
                folder_path = pathlib.Path(remote_target, os.path.dirname(rel_filepath))
                outputs = ssh.exec_command(f'mkdir -p {folder_path.as_posix()}')

                # Actually do the file copy
                destination = pathlib.Path(remote_target, rel_filepath)
                rate = self.time_upload(scp.put, filename, destination.as_posix())
                print(f'  Upload complete. {rate} MB/s')
                all_rates.append(rate)
            except Exception as e:
                errors.append({
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': filename,
                    'destination': destination,
                    'error': str(e),
                    'trace': sys.exc_info()
                })
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
        print(f'Average transfer rate {np.mean(all_rates)} MB/s')

        return {
            'success': successes, 'failure': errors
        }