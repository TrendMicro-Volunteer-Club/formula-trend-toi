#!/bin/sh

if [ $# -lt 1 ]; then
	echo "$(basename $0) [<src_img_file>] <sd_dev_path>{m...n}"
	exit 1;
fi

if [ $(id -u) -ne 0 ]; then
	exec sudo sh $0 "$@";
	exit 1;
fi

PLATFORM="$(uname -s)"

if [ -b "$1" ]; then
	SRC_IMG="$(ls -1 trendcar.*.img | sort -ru | head -n 1)"
	if [ -z "${SRC_IMG}" ]; then
		echo "Image file unspecified"
		exit 1;
	fi
else
	SRC_IMG="$1"; shift;
fi
echo "Using image file ${SRC_IMG}..."

ensure_sd_card_ready ()
{
	local SDCARD="$1"

	if [ "${PLATFORM}" = "Darwin" ]; then
		local SDCARDS1="${SDCARD}s1"
		local SDCARDS2="${SDCARD}s2"
	else
		local SDCARDS1="${SDCARD}1"
		local SDCARDS2="${SDCARD}2"
	fi

	sleep 3;
	while true; do
		if [ -b "${SDCARD}" ] && [ -b "${SDCARDS1}" ]; then
			#echo "Found SD card ${SDCARD}..."
			break;
		fi
		#echo "Waiting for SD card ${SDCARD}..."
		sleep 1;
	done

	#echo "Umounting partitions of ${SDCARD}..."
	if [ "${PLATFORM}" = "Darwin" ]; then
		for partition in $(mount | awk -v SDCARD="${SDCARD}" '$1 ~ "^" SDCARD {print $1}'); do
			diskutil umount ${partition} >/dev/null 2>&1
		done
	else
		for partition in $(mount | awk -v SDCARD="${SDCARD}" '$1 ~ "^" SDCARD {print $1}'); do
			umount ${partition} >/dev/null 2>&1
		done
	fi
	echo "${SDCARD} is Ready"
}

write_sd_card ()
{
	local SDCARD="$1"
	local ndx="$2"
	local tag="$(printf "%-6s" "$(basename "${SDCARD}")")"
	clear
	ensure_sd_card_ready "${SDCARD}" | pv --size 1 --line-mode -c -N "Waiting ${tag}" > /dev/null
	sleep $(( 3 + ${ndx} ))
	clear
	pv -c -N "Writing ${tag}" -p -t -e -r "${SRC_IMG}" | dd of="${SDCARD}" bs=$(( 4 * 1024 * 1024 ))

	if [ "${PLATFORM}" = "Darwin" ]; then
		echo "Ejecting ${SDCARD}...";
		diskutil eject "${SDCARD}"
	fi
}

ndx=1
PIPELINE=""
for disk in $*; do
	if [ ! -z "${PIPELINE}" ]; then
		PIPELINE="|${PIPELINE}";
	fi
	PIPELINE="write_sd_card '${disk}' ${ndx}${PIPELINE}";
	ndx=$(( ${ndx} + 1 ));
done

eval "${PIPELINE}" 

