#!/bin/sh
# Set psql database in backup mode
# WARNING: wal_level needs to be set to replica for this to work!
PSQL="/usr/bin/psql"
PSQL_USER="postgres"
PSQL_DATABASE="<dbname>"
trap "sudo -u $PSQL_USER $PSQL -d $PSQL_DATABASE -c \"select pg_stop_backup();\"" HUP INT QUIT ALRM TERM
# Check psql client is installed
[ -x "$PSQL" ] || exit 0

case "$1" in
    freeze)
        logger "$0 freeze executed"
        # set all configured dbs in backup mode
        sudo -u $PSQL_USER $PSQL -d $PSQL_DATABASE -c "select pg_start_backup('snapshot');" > /dev/null 2>&1 || exit 1
        logger "$0 freeze done"
        exit 0
        ;;
    thaw)
        logger "$0 thaw executed"
        # unset backup mode
        sudo -u $PSQL_USER $PSQL -d $PSQL_DATABASE -c "select pg_stop_backup();" > /dev/null 2>&1 || exit 1
        logger "$0 thaw done"
        exit 0
        ;;
    *)
        exit 1
        ;;
    esac
