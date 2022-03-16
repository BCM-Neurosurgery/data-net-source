#!/bin/bash

# Script to process pose on raw videos
#
# 2022 Gabrielle Strandquist
#
# Given a 2 digit patient ID, script will check for
# access to Wasabi and will iterate over all recorded
# videos on a given date, either user-provided or
# else defaulting to yesterday's date
#
# Each video is passed to the installed OpenPose code
# to estimate joint positions.
# Currently the net_resolution parameter must be
# downgraded due to GPU RAM limitations when processing
# hand or face.
# Given larger GPU RAM, the net_resolution parameter can be
# removed from the OpenPose command
#
# Pose is currently written in OpenPose's example format
# as individual json files per each frame processed.
# Ideally in future this will be updated to a more
# efficient format
#
# To run this script:
# 1) Choose a patient ID, such as 07
# 2) Optionally choose a desired date in an 8-digit format, such as 20211117
# 3) If entering a specific date, run:
#       ./process_pose.sh 07 20211117
#   otherwise run:
#       ./process_pose.sh 07
#

###############################
#check for wasabi being mounted
if [ ! -d "/media/DATA/wasabi_mount" ]
then
    echo "mounting Wasabi..."
    ~/./mount_wasabi.sh
fi
#confirm mount success
if [ ! -d "/media/DATA/wasabi_mount" ]
then
    echo "mounting Wasabi failed!"
    exit 9999 # die with error code 9999
fi
echo "wasabi mounted"

###############################
# Build path from user-provided
# 2-digit patient ID and a
# desired date in YMD form, for
# example Novemeber 17, 2021
# would be 20211117.
# If no date is provided, script
# will default to yesterday's date,
# given that rclone auto-uploads
# every day's recording to Wasabi
# overnight
patient_ID="rcs"$1
#defaults to yesterday's date if no specific date is given
yesterday_date=$(date --date="yesterday" +"%Y%m%d")
date=${2:-$yesterday_date}
echo "Looking for videos to process for patient" $patient_ID "on" $date

wasabi_path="/media/DATA/wasabi_mount/"$patient_ID"/video/"$date"/"
echo "Searching path:" $wasabi_path

###############################
# Check if recordings were made/uploaded
# If no recordings are found, either no videos
# on the provided date exist, or else
# the patient ID wasn't entered correctly,
# in which case script will terminate
if [ ! -d $wasabi_path ]
then
    echo "recordings from yesterday not found on Wasabi, nothing new to process."
    exit 9999 # die with error code 9999
fi

###############################
# Loop through the appropriate
# path and run OpenPose on each
# video.
# Currently pose is written to json
# files in a directory called
# pose_output; ideally this will
# later be updated to a csv format
for dir in "$wasabi_path"*/;do
  echo "searching for videos in:" $dir
  for file in $dir*.avi ;do
      [ -f "$file" ] && echo "Processing pose for '$file'"
      time ./build/examples/openpose/openpose.bin --video $file --hand --write_json pose_output/ --display 0 --render_pose 0 --net_resolution -1x336
  done
done

echo "Pose for all recordings on $date processed!"
