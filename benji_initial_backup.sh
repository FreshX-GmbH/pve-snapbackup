#!/usr/bin/env bash

set -o pipefail

: "${BENJI_LOG_LEVEL:=INFO}"

function _extract_version_uid {
    jq -r '.versions[0].uid'
}

# Returns:
# - version uid in global variable VERSION_UID (empty string on error)
# - stderr output of benji backup in BENJI_BACKUP_STDERR
function benji::backup::ceph::initial {
    local VOLUME="$1"
    local CEPH_POOL="$2"
    local CEPH_RBD_IMAGE="$3"
    local CEPH_RBD_SNAPSHOT=$4
    shift 4
    local VERSION_LABELS=("$@")

    local CEPH_RBD_DIFF_FILE=$(mktemp --tmpdir ceph-rbd-diff-tmp.XXXXXXXXXX)
    local BENJI_BACKUP_STDERR_FILE=$(mktemp --tmpdir benji-backup-tmp.XXXXXXXXXX)

    trap "{ rm -f \"$CEPH_RBD_DIFF_FILE\" \"$BENJI_BACKUP_STDERR_FILE\"; }" RETURN EXIT

    echo "Performing initial backup of $VOLUME:$CEPH_POOL/$CEPH_RBD_IMAGE."

    rbd diff --whole-object "$CEPH_POOL"/"$CEPH_RBD_IMAGE"@"$CEPH_RBD_SNAPSHOT" --format=json >"$CEPH_RBD_DIFF_FILE" \
        || return $?

    VERSION_UID="$(benji -m --log-level "$BENJI_LOG_LEVEL" backup -s "$CEPH_RBD_SNAPSHOT" -r "$CEPH_RBD_DIFF_FILE" \
        $([[ ${#VERSION_LABELS[@]} -gt 0 ]] && printf -- "-l %s " "${VERSION_LABELS[@]}") rbd:"$CEPH_POOL"/"$CEPH_RBD_IMAGE"@"$CEPH_RBD_SNAPSHOT" \
        "$VOLUME" 2> >(tee "$BENJI_BACKUP_STDERR_FILE" >&2) | _extract_version_uid)"
    local EC=$?
    BENJI_BACKUP_STDERR="$(<${BENJI_BACKUP_STDERR_FILE})"
    1>&2 echo "$BENJI_BACKUP_STDERR"
    [[ $EC == 0 ]] || return $EC

    return 0
}

if [ -z $1 ] || [ -z $2 ] || [ -z $3 ]; then
        echo "Usage: $0 [pool] [image] [snapshot]"
        exit 1
else
	NAME="$1/$2"
        rbd snap ls "$1"/"$2" > /dev/null 2>&1
        if [ "$?" != "0" ]; then
                echo "Cannot find rbd image $1/$2."
                exit 2
        fi
        benji::backup::ceph::initial "$NAME" "$1" "$2" "$3"
fi
