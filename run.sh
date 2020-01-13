#! /bin/bash
source /usr/local/bin/benji/activate
# virtualenv is now active.
#
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
cd /data/backup/pvesnapbackup && python script.py | tee /var/log/pvesnapbackup_$DATE.log
exit 0

