#!/bin/bash

# Script to process csvs from jsons
# containing OpenPose keypoints
#
# 2022 Gabrielle Strandquist
#
# Given a 2 digit patient ID, script will check for
# all pose-keypoint jsons as output by OpenPose
# on a given date that is either user-provided
# or else defaulting to yesterday's date
# It will call pose_to_csv.py to convert jsons
# into csv format, assuming that
# the python script is in the same directory.
#
# NOTE: It uses python3 as the command since
# OpenPose is run on machines without Anaconda enabled
#
# To run this script:
# 1) Choose a patient ID, such as 07
# 2) Optionally choose a desired date in an 8-digit format, such as 20211117
# 3) If entering a specific date, run:
#       ./process_csvs.sh 07 20211117
#   otherwise run:
#       ./process_pose.sh 07
#


###############################
# Build path from user-provided
# 2-digit patient ID and a
# desired date in YYYYMMDD form, for
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
echo "Looking for jsons to process for patient" $patient_ID "on" $date

json_path="/media/DATA/"$patient_ID"/pose_2d/"$date"/jsons/"
echo "Searching path:" $json_path

#start csv path
csv_path="/media/DATA/"$patient_ID"/pose_2d/"$date"/csvs/"

###############################
# Check that jsons exist,
# otherwise script will terminate
if [ ! -d $json_path ]
then
    echo "jsons not found in "$json_path", can't process csvs."
    exit 9999 # die with error code 9999
fi

for dir in "$json_path"*/;do
  readarray -d / -t strarr <<<"$dir" #split a string based on the delimiter '/'
  cam_name="${strarr[7]}"
  save_path=$csv_path$cam_name"/"
  # make path for python script to save csv's into
  if [ ! -d $save_path ]
  then
      mkdir -p $save_path
  fi

  echo "searching in camera..." $cam_name
  echo "path to save csv's:" $save_path
  python3 pose_to_csv.py $dir $save_path
done













#
