#!/bin/bash

# Script to test for corrupt/sus behaviors with local videos
# before uploading to Wasabi/deleting local copies
#
# 2022 Gabrielle Strandquist

###############################
# check's videos recorded on today's date
date=$(date --date="today" +"%Y%m%d")
video_path="/media/DATA/rcs07/raw_videos/"$date"/"

for dir in "$video_path"*/;do
  echo $dir
  for file in $dir*.avi ;do
    readarray -d / -t strarr <<<"$file" #split a string based on the delimiter '/'
    readarray -d _ -t strarr <<<"${strarr[8]}"
    vid_name="${strarr[1]}"
    readarray -d - -t strarr <<<"${vid_name}" #split a string based on the delimiter '-'
    file_hour="${strarr[3]}"
    if ! (($file_hour % 2)); then
      echo "$file_hour divisible by 2."
    fi
  done
done
#read n
#if ! ((n % 2)); then
#    echo "$n divisible by 2."
#fi

#python ../video_handler.py "$video_path"
