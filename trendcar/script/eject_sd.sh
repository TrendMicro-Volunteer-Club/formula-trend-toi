#!/bin/sh

if [ $# -lt 1 ]; then
	echo "$(basename $0) <sd_dev_path>"
	exit 1;
fi

if [ $(id -u) -ne 0 ]; then
	exec sudo sh $0 "$@";
	exit 1;
fi

UMOUNT_ONLY=0;

case "$1" in
	--umount-only)	UMOUNT_ONLY=1; shift ;;
esac

###################################################################
SDCARD="$1"
PLATFORM="$(uname -s)"
BOOT="mnt/boot"
ROOT="mnt/root"

umount "${BOOT}"
umount "${ROOT}"

[ -d "${BOOT}" ] && rmdir -p "${BOOT}" 2>/dev/null
[ -d "${ROOT}" ] && rmdir -p "${ROOT}" 2>/dev/null

if [ "${PLATFORM}" = "Darwin" ]; then
	SDCARDS1="${SDCARD}s1"
	SDCARDS2="${SDCARD}s2"

	diskutil umount "${SDCARDS1}" 2>/dev/null
	diskutil umount "${SDCARDS2}" 2>/dev/null

	if [ "${UMOUNT_ONLY}" -eq 0 ]; then
		diskutil eject "${SDCARD}"
	fi
else
	SDCARDS1="${SDCARD}1"
	SDCARDS2="${SDCARD}2"

	umount "${SDCARDS1}" 2>/dev/null
	umount "${SDCARDS2}" 2>/dev/null
fi

