#!/bin/sh

systemctl stop trendcar
sleep 1;

while true; do
	status="$(systemctl status trendcar | awk '$1 == "Active:" {print $2}')"
	if [ "${status}" = "inactive" ] || [ "${status}" = "failed" ]; then
		break;
	fi
done

rm -rf /opt/trendcar.orig
mv -f /opt/trendcar /opt/trendcar.orig

mkdir -p /opt/trendcar
mv -f bin trendcar extra LICENSE /opt/trendcar/
sync; sync; sync

sh /opt/trendcar/bin/trendcar-setup.sh

rm -rf /opt/trendcar.orig

sync; sync; sync
sleep 1;

systemctl start trendcar
exit 0;
