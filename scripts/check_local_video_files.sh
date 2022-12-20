#!/bin/bash

# Script to test for corrupt/sus behaviors with local videos
# before uploading to Wasabi/deleting local copies
#
# 2022 Gabrielle Strandquist

###############################
# check's videos recorded on today's date
date=$(date --date="today" +"%Y%m%d")
video_path="/media/DATA/raw_videos/"$date"/"

for dir in "$video_path"*/;do
  for file in $dir*.avi ;do
    readarray -d / -t strarr <<<"$file" #split a string based on the delimiter '/'
    readarray -d _ -t strarr <<<"${strarr[-1]}"
    vid_name="${strarr[1]}"
    readarray -d - -t strarr <<<"${vid_name}" #split a string based on the delimiter '-'
    file_minute="${strarr[4]}"
    file_minute=${file_minute#0} # strip leading zeros

    # true if minute is NOT evenly divisible by 2;
    # add a "!" before the parenthesis to test if minute IS evenly divisible by 2
    if (($file_minute % 2)); then
      echo "found file with unexpected name: $file. Notifying panic channel!"
      message="Check on videos from $date; avi file naming looks incorrect."
      data="{\"text\": \"$message\"}"
      curl -X POST -H 'Content-type: application/json' --data "$data" https://hooks.slack.com/services/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
      exit
    fi
  done
done

echo "All videos from $date appear correctly named."


