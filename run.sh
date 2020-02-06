#!/usr/bin/env bash
# exit on any error
set -eo pipefail

source /usr/local/benji/bin/activate
# virtualenv is now active.
#
TMPDIR=/tmp/benji
TMPFILE=${TMPDIR}/deep_scrub
SCRUB_MAXAGE=86400
LOGDIR="/var/log/pvesnapbackup"
SQLITE_DB="/data/backup/benji/db/benji.sqlite"
SQLITE_BIN="/usr/bin/sqlite3"
logger "$0 Setting up log directory $LOGDIR"
mkdir -p $LOGDIR
logger "$0 Cleanup old logs in $LOGDIR"
find $LOGDIR -type f -name 'pvesnapbackup_*' -mtime +14 -exec rm {} \;
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
LOGFILE=/var/log/pvesnapbackup/pvesnapbackup_$DATE.log
logger "$0 Sending logs to $LOGFILE"
echo "Checking for locks in benji Database" | tee -a $LOGFILE
if [ "$(echo 'select * from locks;' | $SQLITE_BIN $SQLITE_DB)" != "" ]; then
    echo "backing up database before modifying it" | tee -a $LOGFILE
    cp -v $SQLITE_DB $SQLITE_DB.bak_$(date +%s) |& tee -a $LOGFILE
    TRY=1
    while [ "$(echo 'select * from locks;' | $SQLITE_BIN $SQLITE_DB)" != "" ]; do
        echo "trying to delete locks from database" | tee -a $LOGFILE
        echo "DELETE FROM locks WHERE reason = 'NBD';" | $SQLITE_BIN $SQLITE_DB |& tee -a $LOGFILE
        ((TRY++))
        if [ "$TRY" -gt 5 ]; then
            echo "Failed to unlock database.. giving up" | tee -a $LOGFILE 
            exit 1
        fi
    done
fi
echo "Starting backup expiration" | tee -a $LOGFILE
benji enforce latest3,days7,weeks4,months12 | tee -a $LOGFILE
cd /data/backup/pvesnapbackup && python -u backupWrapper.py |& tee -a $LOGFILE
# Start deep scrubbing if it did not run for more than 24 hours
if [ ! -d /tmp/benji ]; then
    mkdir $TMPDIR
    touch $TMPFILE
fi
if [ ! -e /tmp/benji/deep_scrub ]; then
    touch $TMPFILE
fi
MTIME=$(stat -c %Y $TMPFILE)
NOW=$(date +%s)
LASTSCRUB=$(( $NOW-$MTIME ))
if [ $LASTSCRUB -gt $SCRUB_MAXAGE ]; then
    echo "Starting deep scrubbing of 14 % of all images" |& tee -a $LOGFILE
    benji batch-deep-scrub --version-percentage 14 | tee -a $LOGFILE && touch $TMPFILE
    INVALID=$(benji -m --log-level ERROR ls | jq -r '.versions[] | select(.status|test("invalid"))| .uid, .status' | wc -l)
    if [ $INVALID -ne 0 ]; then 
        echo "One or more backups are invalid! Manual intervention needed!" |& tee -a $LOGFILE
        benji ls 'status != "valid"' | mail -s "Invalid Benji backups found! Please check!" florian@freshx.de
    fi
fi

exit 0