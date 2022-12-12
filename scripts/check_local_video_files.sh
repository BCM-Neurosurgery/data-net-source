#!/bin/bash

# Script to test for corrupt/sus behaviors with local videos
# before uploading to Wasabi/deleting local copies
#
# 2022 Gabrielle Strandquist

###############################
# check's videos recorded on today's date
date=$(date --date="today" +"%Y%m%d")
video_path="/media/DATA/rcs07/raw_videos/"$date"/"


python ../video_handler.py "$video_path"
