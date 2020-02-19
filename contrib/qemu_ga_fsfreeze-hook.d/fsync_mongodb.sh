#!/bin/sh
# Set psql database in backup mode
MONGO="/usr/bin/mongo"
MONGO_USER="admin"
MONGO_PWD="***"
trap "unlock" HUP INT QUIT ALRM TERM
# Check mysql is installed and the server running
[ -x "$MONGO" ] && $MONGO -u $MONGO_USER -p $MONGO_PWD --eval "db.ping;" > /dev/null || exit 0

unlock () {
    $MONGO -u $MONGO_USER -p $MONGO_PWD --eval "db.fsyncUnlock();" > /dev/null 2>&1
}

lock () {
    $MONGO -u $MONGO_USER -p $MONGO_PWD --eval "db.fsyncLock();" > /dev/null 2>&1
}

case "$1" in
    freeze)
        logger "$0 freeze executed"
        # set all configured dbs in backup mode
        lock
        ;;
    thaw)
        logger "$0 thaw executed"
        # unset backup mode
        unlock
        ;;
    *)
        exit 1
        ;;
esac

