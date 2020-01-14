#! /bin/bash
source /usr/local/benji/bin/activate
# virtualenv is now active.
#
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
LOGFILE=/var/log/pvesnapbackup_$DATE.log
echo "Starting backup expiration" | tee $LOGFILE
benji enforce latest3,days7,weeks4,months12 | tee $LOGFILE
cd /data/backup/pvesnapbackup && python backupWrapper.py | tee $LOGFILE
echo "Starting deep scrubbing of 14 % of all images" | tee $LOGFILE
benji batch-deep-scrub --version-percentage 14 | tee $LOGFILE 
INVALID=$(benji -m --log-level ERROR ls | jq -r '.versions[] | select(.status|test("invalid"))| .uid, .status' | wc -l)
if [ $INVALID -ne 0 ]; then 
    echo "One or more backups are invalid! Manual intervention needed!" | tee $LOGFILE
    benji ls 'status != "valid"' | mail -s "Invalid Benji backups found! Please check!" florian@freshx.de
fi
exit 0

