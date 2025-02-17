#!/bin/bash
#
# Script to detect freezes in raw videos
#
# 2022 Gabrielle Strandquist
#
# Given a 2 digit patient ID, script will check for
# access to Wasabi and will iterate over all recorded
# videos on a given date, either user-provided or
# else defaulting to yesterday's date
#
# Can also process videos from a single camera only,
# if given the  name of the camera. Otherwise assumes
# all cameras should be processed
#
# To run this script:
# 1) Choose a patient ID, such as 07
# 2) Optionally choose a desired date in an 8-digit format, such as 20211117
#    and optionally can choose to process only a single camera.
# 3) If entering a specific date, run:
#       ./detect_freeze.sh 07 20211117
#    or for a specfic date + specific camera:
#       ./detect_freeze.sh 07 20211117 video8
#   otherwise run:
#       ./detect_freeze.sh 07
#

###############################
# check for wasabi being mounted
# things get weird if you try
# to mount when it's already
# mounted; best to do this
# separately from this script
if [ ! -d "/media/DATA/wasabi_mount" ]
then
    echo "please mount Wasabi before proceeding!"
    exit 9999 # die with error code 9999
fi
echo "wasabi mounted"

###############################
# Build path from user-provided
# 2-digit patient ID and a
# desired date in YMD form, for
# example November 17, 2021
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
echo "Looking for videos for patient" $patient_ID "on" $date


###############################
# Build base path
wasabi_path="/media/DATA/wasabi_mount/"$patient_ID"/video/"$date"/"

###############################
# Check if recordings were made/uploaded
# If no recordings are found, either no videos
# on the provided date exist, or else
# the patient ID wasn't entered correctly,
# in which case script will terminate
if [ ! -d $wasabi_path ]
then
    echo "recordings not found on Wasabi, nothing new to process."
    exit 9999 # die with error code 9999
fi

###############################
#allow the option of processing only one camera at a time
single_camera=$3


###############################
# Loop through the appropriate
# path and run a freeze detection
# on each video.
# The output is written to a
# separate txt file/video, and
# if the txt file size is 0,
# no freezes have been detected
# I'll find some way to check
# this in a shell script,
# to get the relavent sections
# where freezes where found


for dir in "$wasabi_path"*/;do
    if [[ "$dir" == *"$single_camera"* ]]; then
      # make dir for detected freezes txt files
      mkdir detected_freezes

      for file in $dir*.avi ;do
          readarray -d / -t strarr <<<"$file" #split a string based on the delimiter '/'
          readarray -d _ -t strarr <<<"${strarr[8]}" #split a string based on the delimiter '_'
          cam_name="${strarr[0]}"
          vid_name="${strarr[1]}"
          readarray -d . -t strarr <<<"${vid_name}" #split a string based on the delimiter '.'

          full_path=$json_dir$cam_name"/${strarr[0]}"
          if [ ! -d "$full_path" ]
          then mkdir -p "$full_path"
          fi

          [ -f "$file" ] && echo "detecting freezes in '$file'"
          #make txt file name

          ffmpeg -i "$file" -vf "freezedetect=n=-60dB:d=2, metadata=mode=print:file=freeze_$file.txt" -map 0:v:0 -f null -;
      done
    echo "Pose for all recordings on $date processed!"

  else
    echo "no videos found for camera" $single_camera "on" $date "in path" $dir
  fi
done

for i in *.mkv; do
  ffmpeg -i "$i" -vf "freezedetect=n=-60dB:d=2, metadata=mode=print:file=freeze_$i.txt" -map 0:v:0 -f null -;
done
