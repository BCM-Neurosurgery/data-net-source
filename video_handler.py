import os
from datetime import datetime
import logging
import subprocess

from .pose_estimation import do_2d_pose, do_3d_pose, upload_pose


VIDEO_SRC = '/media/DATA/video'
POSE_2D_SRC = '/media/DATA/pose_2d'


class UploadError(Exception):
    pass


def preprocess():
    """"""


def upload_raw(folder):
    """Spool up an independent process to upload the 'raw' videos to Wasabi"""
    uploader = subprocess.Popen(
        ['rclone', 'move',
         f'/media/DATA/{folder}', f'secret_sauce:/rcs07/video/{folder}',
         '>>', '/home/python_rclone.log', '2>&1'],
    )
    return uploader


def verify_video_upload(folder):
    """
    Check whether the videos in a folder have been correctly uploaded to remote via rclone

    :param folder: folder to check on rclone. Assumed to be a video folder
    :return: boolean. Whether or not the upload was successful
    """
    return verify_rclone_upload(
        'raw_video_upload',
        f'/media/DATA/raw_videos/{folder}',
        f'secret_sauce:/rcs07/video/{folder}'
    )


def verify_pose_upload(folder):
    """
    Check whether the videos in a folder have been correctly uploaded to remote via rclone

    :param folder: folder to check on rclone. Assumed to be a video folder
    :return: boolean. Whether or not the upload was successful
    """
    return verify_rclone_upload(
        'pose_result_upload',
        f'/media/DATA/pose_2d/{folder}',
        f'secret_sauce:/rcs07/pose_2d/{folder}'
    ) # and verify_rclone_upload(<3d pose equivalent>)


def verify_rclone_upload(check_name, source, destination):
    """
    Verify that the contents of the given folder have been uploaded to the rclone remote

    Run rclone's verify function, dump it to a log file, and then parse the result to find signs of fatal differences.
    Fatal differences are considered to be:
        - `+ path` means path was missing on the destination, so only in the source
        - `* path` means path was present in source and destination but different.
        - `! path` means there was an error reading or hashing the source or dest.

    :param check_name: name of the check being run, for logging purposes
    :param source: full path to the data source directory
    :param destination: full path to the expected destination (including remote)
    """

    check_file_name = f'/home/{check_name}_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
    checker = subprocess.Popen(
        ['rclone', 'check', '--one-way', source, destination, '>>', check_file_name, '2>&1']
    )
    checker.wait()

    with open(check_file_name) as cf:
        check_result = cf.read()

    success = True
    if '+ ' in check_result or '* ' in check_result or '! ' in check_result:
        logging.error(f'Failed {check_name}! Check {check_file_name} for more details!')
        success = False
    return success


def pose_estimation(source_folder):
    """Wildly inadequate placeholder"""
    # Start 2d pose estimation and wait f
    pose_estimator = do_2d_pose()
    uploader = upload_pose()
    return uploader


def cleanup(source_folder, uploader, pose_manager):

    # Wait for these processes to complete
    upload_result = uploader.wait()
    pose_result = pose_manager.wait()

    # Verify successful completion
    if upload_result or pose_result:    # If a non-zero exit code is returned anywhere assume something failed
        logging.error(f'Received a non-zero video handler exit code!\n'
                      f'  Raw Video Uploader Returned: {upload_result}\n'
                      f'  Pose Estimation Returned: {pose_result}')
        raise UploadError('Async processes failed to complete. Stopping cleanup')

    # Verify that the raw_video upload was correct
    if not verify_video_upload(source_folder):
        logging.error(f'Failed to upload raw video to remote storage!')
        raise UploadError('Remote video integrity check failed. Stopping cleanup')

    # Verify that the raw_video upload was correct
    if not verify_pose_upload(source_folder):
        logging.error(f'Failed to upload raw video to remote storage!')
        raise UploadError('Remote video integrity check failed. Stopping cleanup')

    # Only reached if all the above checks succeeded.
    # Remove now un-needed raw input data
    os.remove(os.path.join(VIDEO_SRC, source_folder))
    os.remove(os.path.join(POSE_2D_SRC, source_folder))


def notify_server():
    """Either socket or ray magic to let the server know video has been uploaded"""


def handle_new_videos(source_folder):
    """Top level function to handle all new videos in a given directory"""
    preprocess()

    # Begin uploading raw video asynchronously
    raw_uploader = upload_raw(source_folder)

    # Begin processing pose in 2/3d potentially use cluster
    pose_uploader = pose_estimation(source_folder)

    # Wait for completion of all above processes
    # Verify that everything has succeeded and un-necessary raw video
    cleanup(source_folder, raw_uploader, pose_uploader)

    notify_server()


if __name__ == "__main__":
    handle_new_videos('test_source')