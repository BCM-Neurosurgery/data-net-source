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
# Can also process a single camera only, if given the
# name of the camera. Otherwise assumes all cameras
# should be processed
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
#    and optionally can choose a single camera
#    and/or a single hour of video to process
# 3) If entering a specific date, run:
#       ./process_pose.sh 07 20211117
#    or for a specfic date + specific camera:
#       ./process_pose.sh 07 20211117 video8
#    or for a specfic date + single hour:
#       ./process_pose.sh 07 20211117 14
#    or for a specfic date + specific camera + single hour:
#       ./process_pose.sh 07 20211117 video8 14
#   otherwise run:
#       ./process_pose.sh 07
#

###############################
# check for central server being mounted
# things get weird if you try
# to mount when it's already
# mounted; best to do this
# separately from this script
if [ ! -d "/media/BigData" ]
then
    echo "please mount data before proceeding!"
    exit 9999 # die with error code 9999
fi
echo "central server RAID data mounted"

###############################
# Build path from user-provided
# 2-digit patient ID and a
# desired date in YMD form, for
# example Novemeber 17, 2021
# would be 20211117.
# If no date is provided, script
# will default to yesterday's date
patient_ID="rcs"$1
#defaults to yesterday's date if no specific date is given
yesterday_date=$(date --date="yesterday" +"%Y%m%d")
date=${2:-$yesterday_date}
echo "Looking for videos to process for patient" $patient_ID "on" $date


###############################
# Build base path
raid_data_path="/media/BigData/"$patient_ID"/video/"$date"/"


###############################
# Check if recordings were made/uploaded
# If no recordings are found, either no videos
# on the provided date exist, or else
# the patient ID wasn't entered correctly,
# in which case script will terminate
if [ ! -d $raid_data_path ]
then
    echo "recordings not found on central server, nothing new to process."
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
#
# Start directory name variable
json_dir="/media/DATA/"$patient_ID"/pose_2d/"$date"/jsons/"

###############################
#allow the option of processing only one camera at a time
single_camera=''
single_hour=''

if [ ! -z "$3" ];then
  if [[ $3 =~ ^[+-]?[0-9]+$ ]];then
    echo "A single hour was selected for processing:" $3
    single_hour=$3
  else
    echo "Processing videos from camera" $3
    single_camera=$3
  fi
else
  echo "Processing all videos from all cameras on" $date
fi

# allow the option of processing only 1 hour's worth of pose
if [ ! -z "$4" ];then
  if [[ $4 =~ ^[+-]?[0-9]+$ ]];then
    echo "A single hour was selected for processing:" $4
    single_hour=$4
  else
    echo "A valid integer was not given, so the entire day's videos will be processed."
  fi
fi


for dir in "$raid_data_path"*/;do
    if [[ "$dir" == *"$single_camera"* ]]; then
      for file in $dir*.avi ;do

          readarray -d / -t strarr <<<"$file" #split a string based on the delimiter '/'
          readarray -d _ -t strarr <<<"${strarr[7]}" #split a string based on the delimiter '_'

          cam_name="${strarr[0]}"
          vid_name="${strarr[1]}"
          readarray -d . -t strarr <<<"${vid_name}" #split a string based on the delimiter '.'
          vid_path="${strarr[0]}"
          full_path=$json_dir$cam_name"/$vid_path"

            # if single-hour arg is valid int
            if [[ $single_hour =~ ^[+-]?[0-9]+$ ]];then
              # if file not in range of single-hour
              readarray -d - -t strarr <<<"${vid_name}" #split a string based on the delimiter '-'
              file_hour="${strarr[3]}"
              file_hour=${file_hour#0} # strip leading zeros
              if (( $file_hour != $single_hour )); then
                echo "file" $file "not in desired hour" $single_hour", skipping."
                continue
              fi
            fi


          if [ ! -d "$full_path" ]
          then mkdir -p "$full_path"
          fi

          [ -f "$file" ] && echo "Processing pose for '$file'"
          echo "saving to" $full_path
          echo ""
          time ./build/examples/openpose/openpose.bin --video $file --hand --face --write_json $full_path --display 0 --render_pose 0
      done

  else
    echo "no videos found for camera" $single_camera "on" $date "in path" $dir
  fi
done
