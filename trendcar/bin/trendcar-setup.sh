#!/bin/sh

if [ ! -e "/sys/firmware/devicetree/base/model" ]; then
	echo "This shell script can only be executed in Raspberry Pi"
	exit 1;
fi

if [ $(id -u) -ne 0 ]; then
	exec sudo sh $0 "$@";
	exit 1;
fi
export LANG=C LC_ALL=C

#####################################################################
# Ensure trendcar executables are ready

chown -R pi.pi /opt/trendcar
chmod a+x /opt/trendcar/bin/*.sh

for script in /opt/trendcar/bin/trendcar-*; do
	chmod a+x "${script}";
	ln -sf "${script}" "/usr/bin/$(basename "${script}")"
done

#####################################################################
# Update scripts to display info

if egrep -q '^\s*#?\s*echo\s+(-n\s+)?"@?ipaddr="\s*;\s*hostname\s+-I' /home/pi/.bashrc 2>/dev/null; then
	sed -i -e 's/^\s*#\?\s*echo\s\+\(-n\s\+\)\?"@\?ipaddr="\s*;\s*hostname\s\+-I.*$/echo -n "@ipaddr=";hostname -I/' /home/pi/.bashrc
else
	echo 'echo -n "@ipaddr=";hostname -I' >> /home/pi/.bashrc
fi

if egrep -q '^macaddr=' /boot/identity.txt 2>/dev/null; then
	sed -i -e 's/^\s*\([A-Za-z]\+\s*=.*\)$/@\1/' /boot/identity.txt

	START_TAG="START_OF_HOSTNAME_PASSWORD_CHANGING_SCRIPT"
	END_TAG="END_OF_HOSTNAME_PASSWORD_CHANGING_SCRIPT"
	sed -i -e '/^\s*\#\s*'"${START_TAG}"'.*$/,/^\s*\#\s*'"${END_TAG}"'.*$/s/echo "hostname=/echo "@hostname=/g'      /etc/rc.local
	sed -i -e '/^\s*\#\s*'"${START_TAG}"'.*$/,/^\s*\#\s*'"${END_TAG}"'.*$/s/echo "passwd=/echo "@passwd=/g'          /etc/rc.local
	sed -i -e '/^\s*\#\s*'"${START_TAG}"'.*$/,/^\s*\#\s*'"${END_TAG}"'.*$/s/echo "macaddr=/echo "@macaddr=/g'        /etc/rc.local
	sed -i -e '/^\s*\#\s*'"${START_TAG}"'.*$/,/^\s*\#\s*'"${END_TAG}"'.*$/s/\(awk.*~\s*\/\)\(macaddr\/\s*\)/\1@\2/g' /etc/rc.local
fi

#####################################################################
# Modify for usbmount

sed -i -e 's/^\(\s*MountFlags\s*=\s*\)slave\(\s*.*\)$/\1shared\2/' /lib/systemd/system/systemd-udevd.service
systemctl daemon-reload

cat > /etc/usbmount/mount.d/01_trendcar <<EOF
#!/bin/sh
[ -d "\${UM_MOUNTPOINT}" ] || exit 0;

autorun_sh="\${UM_MOUNTPOINT}/autorun.sh"
if [ -r "\${autorun_sh}" ]; then
	sh "\${autorun_sh}"
fi

autorun_zip="\${UM_MOUNTPOINT}/autorun.zip"
if [ -r "\${autorun_zip}" ]; then
	autorun_temp_folder="/tmp/autorun_zip"
	rm -rf "\${autorun_temp_folder}"
	mkdir -p "\${autorun_temp_folder}"
	cd "\${autorun_temp_folder}"; 7za x "\${autorun_zip}"

	if [ -r "\${autorun_temp_folder}/autorun.sh" ]; then
		cd "\${autorun_temp_folder}"; sh ./autorun.sh
	fi
	rm -rf "\${autorun_temp_folder}";
fi
exit 0;
EOF
chmod a+x /etc/usbmount/mount.d/01_trendcar

#####################################################################
# Setup /etc/screenrc

sed -i -e '/^\s*bind\s\+[=_+-]\s\+/d' /etc/screenrc
cat >> /etc/screenrc <<-EOF_SCREENRC
bind = resize =
bind _ resize max
bind - resize -1
bind + resize +1
EOF_SCREENRC

#####################################################################
# Enable firewall
systemctl enable netfilter-persistent
systemctl start netfilter-persistent

iptables -P INPUT   ACCEPT
iptables -P OUTPUT  ACCEPT
iptables -P FORWARD ACCEPT
iptables -N IN_TRENDCAR >/dev/null 2>&1
iptables -F
iptables -t nat -F
iptables -A INPUT -i usb0 -j ACCEPT
iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -m state --state NEW --syn -j ACCEPT
iptables -A INPUT -p udp --dport 68 -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT
iptables -A INPUT -p udp -m multiport --dports 5353 -j ACCEPT
iptables -A INPUT -j IN_TRENDCAR
iptables -A INPUT -j DROP
iptables -A IN_TRENDCAR -j RETURN
iptables-save > /etc/iptables/rules.v4

ip6tables -P INPUT   DROP
ip6tables -P OUTPUT  DROP
ip6tables -P FORWARD DROP
ip6tables -F
ip6tables-save > /etc/iptables/rules.v6

systemctl restart netfilter-persistent

#####################################################################
# Enable waiting for DHCP at boot
if [ ! -r /etc/systemd/system/dhcpcd.service.d/wait.conf ]; then
	mkdir -p /etc/systemd/system/dhcpcd.service.d

	cat > /etc/systemd/system/dhcpcd.service.d/wait.conf <<-EOF
	[Service]
	ExecStart=
	ExecStart=/usr/lib/dhcpcd5/dhcpcd -q -w
	EOF
fi

# Enable pinging the router after obtaining DHCP to renew the ARP entry in the router
cat <<EOF > /etc/dhcp/dhclient-exit-hooks.d/reach_router
reach_router ()
{
	default_route="\$(/sbin/ip route show | awk '\$1=="default"{print \$3}')";
	if [ ! -z "\${default_route}" ]; then
		for i in \$(seq 1 3); do
			if ping -q -c 3 "\${default_route}"; then
				break;
			fi
		done
	fi
}

case \${reason} in
    BOUND|RENEW|REBIND|REBOOT|EXPIRE|FAIL|RELEASE|STOP|TIMEOUT)
	reach_router;
    ;;
esac
EOF

#####################################################################
# Adjust warning level
warning_level=1
if grep -q "avoid_warnings=" /boot/config.txt; then
	sed -i -e "s/\(avoid_warnings\s*=\s*\).*$/\1${warning_level}/" /boot/config.txt
else
	echo "avoid_warnings=${warning_level}" >> /boot/config.txt
fi

# Minimize GPU memory usage
gpu_mem=0
if grep -q "gpu_mem=" /boot/config.txt; then
	sed -i -e "s/\(gpu_mem\s*=\s*\).*$/\1${gpu_mem}/" /boot/config.txt
else
	echo "gpu_mem=${gpu_mem}" >> /boot/config.txt
fi

#####################################################################
# setup default locale for terminal
if ! grep -q "export LANG=C LC_ALL=C" ~pi/.bashrc; then
	echo "export LANG=C LC_ALL=C" >> ~pi/.bashrc
fi

#####################################################################
# apply patches
patch_keras ()
{
	#patch /usr/local/lib/python{2.7,3.5}/dist-packages/keras/engine/saving.py

	local ver="$1"; shift;
	local folder="/usr/local/lib/python${ver}/dist-packages/keras/engine/";

	if [ ! -d "${folder}" ] || [ ! -e "${folder}/saving.py" ]; then
		return;
	fi

(cd ${folder}; patch -p0 -N $* ) <<EOF
--- saving.py	2018-11-09 11:19:09.243253099 +0000
+++ saving.py	2018-11-08 09:57:34.505426000 +0000
@@ -134,6 +134,7 @@
                 'loss': model.loss,
                 'metrics': model.metrics,
                 'sample_weight_mode': model.sample_weight_mode,
+                'weighted_metrics': model.weighted_metrics,
                 'loss_weights': model.loss_weights,
             }, default=get_json_type).encode('utf8')
             symbolic_weights = getattr(model.optimizer, 'weights')
EOF
}
patch_keras 2.7 --dry-run && patch_keras 2.7
patch_keras 3.5 --dry-run && patch_keras 3.5

#####################################################################
# upgrade opencv-3.x for python2.7/python3

python_opencv_version="3.4.3"
python_opencv_install_basedir="/usr/local/lib"
python_opencv_source_basedir="/opt/trendcar/extra"
python_opencv_package="${python_opencv_source_basedir}/python-opencv-${python_opencv_version}.tgz"
python_opencv_library_path="${python_opencv_install_basedir}/opencv"
python_opencv_installed_version="$(cat "${python_opencv_library_path}/VERSION" 2>/dev/null)"

if [ ! "${python_opencv_version}" = "${python_opencv_installed_version}" ]; then
	if [ -r "${python_opencv_package}" ]; then
		rm -f "${python_opencv_install_basedir}/opencv"
		tar -C "${python_opencv_install_basedir}" -xzf "${python_opencv_package}";
		echo "${python_opencv_library_path}" > /etc/ld.so.conf.d/opencv.conf
		ldconfig
	fi
	chown -R root:staff "${python_opencv_library_path}"
fi

for py in python2.7 python3.5; do
	cat > /usr/bin/${py}-cv3 <<-EOF
	#!/bin/sh
	export LD_LIBRARY_PATH="${python_opencv_library_path}:${LD_LIBRARY_PATH}";
	export PYTHONPATH="${python_opencv_library_path}/${py}:${PYTHONPATH}";
	exec /usr/bin/${py} "\$@"
	EOF
	chmod a+x /usr/bin/${py}-cv3
done

ln -sf python2.7-cv3 /usr/bin/python-cv3
ln -sf python2.7-cv3 /usr/bin/python2-cv3
ln -sf python3.5-cv3 /usr/bin/python3-cv3

#####################################################################
sync; sync; sync
echo 3 > /proc/sys/vm/drop_caches

