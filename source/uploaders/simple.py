import os
import shutil
import sys
import pathlib
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
                print(f'Copying to {destination}')
                shutil.copy(filename, destination)
                print(f'  Done')
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
    This uploader expects a target location of the form
    ['host', '/base/path/on/remote']
    """

    uploader_name = 'SCPUploader'

    def upload(self, ready):
        # Local imports used only here
        from paramiko import SSHClient
        from scp import SCPClient

        errors = ready['failure']
        successes = ready['to upload']

        # Set up the ssh client and associated scp transport
        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(self.target_location[0])
        scp = SCPClient(ssh.get_transport())

        remote_target = self.target_location[1]

        for filename in ready:
            destination = 'Failed to determine!'
            try:
                rel_filepath = os.path.relpath(filename, start=self.source_location)

                # Make sure the destination folder exists using ssh. We assume a *nix destination
                # This solution is a bit hacky, likely executes a lot more commands than necessary
                folder_path = pathlib.PosixPath(remote_target, os.path.dirname(rel_filepath))
                outputs = ssh.exec_command(f'mkdir -p {folder_path}')

                # Actually do the file copy
                destination = pathlib.PosixPath(remote_target, rel_filepath)
                scp.put(filename, destination)
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

        # Make sure we close the transports
        scp.close()
        ssh.close()

        return {
            'success': successes, 'failure': errors
        }