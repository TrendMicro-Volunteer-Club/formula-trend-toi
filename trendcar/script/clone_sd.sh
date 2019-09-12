#!/bin/sh

if [ $# -lt 1 ]; then
	echo "$(basename $0) <sd_dev_path> [<dest_img_file>]"
	exit 1;
fi

if [ $(id -u) -ne 0 ]; then
	exec sudo sh $0 "$@";
	exit 1;
fi

SDCARD="$1"
DEST_IMG="${2-trendcar.$(date '+%Y%m%d').img}"

./prepare_sd.sh --publish "${SDCARD}"
./eject_sd.sh --umount-only "${SDCARD}"

total_size="$(fdisk -d /dev/disk2 | awk -F, '
	{
		end = $1 + $2;
		if (end > last_end) {
			last_end = end
		}
	}
	END {
		print ((last_end + 1) * 512);
	}
')"

echo "Cloning image ${SDCARD} of ${total_size} bytes to ${DEST_IMG}...";

if hash pv 2>/dev/null; then
	dd if="${SDCARD}" bs=512 count=$(( ${total_size}/512 )) 2>/dev/null | pv -p -t -e -r -s "${total_size}" > "${DEST_IMG}"
else
	time dd if="${SDCARD}" bs=512 count=$(( ${total_size}/512 )) of="${DEST_IMG}"
fi

shasum -a 256 "${DEST_IMG}" > "${DEST_IMG}.sha256"

