#!/bin/bash

# Script to process pose on raw videos
#
# 2022 Gabrielle Strandquist
#
# Given a 2 digit patient ID, script will check for
# access to Wasabi and will iterate over all recorded
# videos on a given date, from dates listed in batch_pose_dates.txt
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
# 2) Run:
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
# Build path from dates in the
# batch_pose_dates.txt file
patient_ID="rcs"$1
batch_dates="/home/gsquist/openpose/batch_pose_dates.txt"

# ###############################
# # Build base path
raid_data_path="/media/BigData/"$patient_ID"/video/"

###############################
# Loop through the appropriate
# path and run OpenPose on each
# video.
# Currently pose is written to json
# files in a directory called
# pose_output; ideally this will
# later be updated to a csv format
#


while IFS= read -r date_line
do
  data_path=$raid_data_path$date_line"/"
  if [ ! -d $data_path ]
  then
      echo "recordings not found in $data_path, check path!"
  else
    echo "processing" $date_line

    # Start directory name variable
    json_dir="/media/DATA/"$patient_ID"/pose_2d/"$date_line"/jsons/"

    for dir in "$data_path"*/;do
        echo "searching $dir for videos to process"
      for file in $dir*.avi ;do
          readarray -d / -t strarr <<<"$file" # split a string based on the delimiter '/'
          readarray -d _ -t strarr <<<"${strarr[7]}" # split a string based on the delimiter '_'
          cam_name="${strarr[0]}"
          vid_name="${strarr[1]}"
          readarray -d . -t strarr <<<"${vid_name}" #split a string based on the delimiter '.'
          vid_path="${strarr[0]}"
          full_path=$json_dir$cam_name"/$vid_path"

          if [ ! -d "$full_path" ]
          then mkdir -p "$full_path"
          fi
          [ -f "$file" ] && echo "Processing pose for '$file'"
          echo "saving to" $full_path
          # time ./build/examples/openpose/openpose.bin --video $file --hand --face --write_json $full_path --display 0 --render_pose 0
          echo ""
      done

    done
  fi

done < "$batch_dates"
echo "finished processing" $batch_dates
