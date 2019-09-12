#!/bin/sh

if [ $# -lt 1 ]; then
	echo "$(basename $0) <sd_dev_path> [<src_img_file>]"
	exit 1;
fi

if [ $(id -u) -ne 0 ]; then
	exec sudo sh $0 "$@";
	exit 1;
fi

PLATFORM="$(uname -s)"
if [ "${PLATFORM}" = "Darwin" ]; then
	SDCARD="${1-/dev/disk2}"
	SDCARDS1="${SDCARD}s1"
	SDCARDS2="${SDCARD}s2"
else
	SDCARD="$1"

	if [ -z "${SDCARD}" ]; then
		echo "SD block device was unspecified"
		exit 1;
	fi
	SDCARDS1="${SDCARD}1"
	SDCARDS2="${SDCARD}2"
fi

SRC_IMG="${2-trendcar.$(date '+%Y%m%d').img}"

ensure_sd_card_ready ()
{
	sleep 3;
	while true; do
		if [ -b "${SDCARD}" ] && [ -b "${SDCARDS1}" ]; then
			echo "Found SD card ${SDCARD}...";
			break;
		fi
		echo "Waiting for SD card ${SDCARD}...";
		sleep 1;
	done

	echo "Umounting partitions of ${SDCARD}...";
	if [ "${PLATFORM}" = "Darwin" ]; then
		for partition in $(mount | awk -v SDCARD="${SDCARD}" '$1 ~ "^" SDCARD {print $1}'); do
			diskutil umount ${partition}
		done
	else
		for partition in $(mount | awk -v SDCARD="${SDCARD}" '$1 ~ "^" SDCARD {print $1}'); do
			umount ${partition}
		done
	fi
}

ensure_sd_card_ready

echo "Writing image ${SRC_IMG} to ${SDCARD}...";

if hash pv 2>/dev/null; then
	pv -p -t -e -r "${SRC_IMG}" | dd of="${SDCARD}" bs=$(( 4 * 1024 * 1024 ))
else
	time dd if="${SRC_IMG}" bs=$(( 4 * 1024 * 1024 )) of="${SDCARD}"
fi

if [ "${PLATFORM}" = "Darwin" ]; then
	echo "Ejecting ${SDCARD}...";
	diskutil eject "${SDCARD}"
fi

