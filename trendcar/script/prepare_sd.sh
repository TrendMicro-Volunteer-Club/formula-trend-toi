#!/bin/sh

if [ $# -lt 1 ]; then
	echo "$(basename $0) <sd_dev_path> [<raspbian_image_path>]"
	exit 1;
fi

if [ $(id -u) -ne 0 ]; then
	exec sudo sh $0 "$@";
	exit 1;
fi

MOUNT_ONLY=0;
PUBLISH=0;

case "$1" in
	--mount-only)	MOUNT_ONLY=1; shift ;;
	--publish)      PUBLISH=1; shift; ;;
esac

###################################################################
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

SRC_IMG="$2"

BOOT="mnt/boot"
ROOT="mnt/root"
AUTOLOGIN_USER="pi"
SCRIPT_SELF="$0"
SCRIPT_BASEDIR="$(cd "$(dirname ${SCRIPT_SELF})"; pwd)"
SOURCE_BASEDIR="$(cd "${SCRIPT_BASEDIR}/.."; pwd)"

###################################################################

waiting_sd_card_ready ()
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
}

extract_image_to_sd ()
{
	if [ -z "${SRC_IMG}" ]; then
		echo "Source image was unspecified. Skipped writing image to ${SDCARD}...";
		return;
	fi

	waiting_sd_card_ready
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

	echo "Writing image ${SRC_IMG} to ${SDCARD}...";
	if hash pv 2>/dev/null; then
		dd if=${SRC_IMG} 2>/dev/null | pv -p -t -e -r -s $(( $(du "${SRC_IMG}" | cut -f1) * 512 )) | dd of=${SDCARD} bs=$((4*1024*1024)) 2>/dev/null
	else
		time dd if=${SRC_IMG} of=${SDCARD} bs=$((4*1024*1024))
	fi
}

mount_sd_partitions ()
{
	waiting_sd_card_ready 

	umount ${SDCARDS1} >/dev/null 2>&1
	umount ${SDCARDS2} >/dev/null 2>&1

	mkdir -p "${BOOT}"
	mkdir -p "${ROOT}"

	if [ "${PLATFORM}" = "Darwin" ]; then
		mount -t msdos ${SDCARDS1} "${BOOT}"
		fuse-ext2 -o force,allow_other ${SDCARDS2} "${ROOT}"
	else
		mount ${SDCARDS1} "${BOOT}"
		mount ${SDCARDS2} "${ROOT}"
	fi
}

modify_config_value ()
{
	local CONFIG_TXT="${BOOT}/config.txt"
	local key=$1
	local value=$2
	local subvalue=$3

	if ! grep -q "^\s*${key}\s*=\s*${value}\s*$" "${CONFIG_TXT}"; then
		if [ "${key}" = "dtoverlay" ]; then
			if grep -q "^\s*#\s*${key}\s*=\s*${value}\s*$" "${CONFIG_TXT}"; then
				sed -i "" -e "s/^[[:space:]]*#[[:space:]]*\(${key}[[:space:]]*=[[:space:]]*\).*$/\1${value}/" "${CONFIG_TXT}";
				return;
			fi
		elif [ "${key}" = "dtparam" ]; then
			if grep -q "^\s*${key}\s*=\s*${value}\s*=" "${CONFIG_TXT}"; then
				sed -i "" -e "s/^[[:space:]]*\(${key}[[:space:]]*=[[:space:]]*${value}\)[[:space:]]*=.*$/\1=${subvalue}/" "${CONFIG_TXT}";
				return;
			elif grep -q "^\s*#\s*${key}\s*=\s*${value}\s*=" "${CONFIG_TXT}"; then
				sed -i "" -e "s/^[[:space:]]*#[[:space:]]*\(${key}[[:space:]]*=[[:space:]]*${value}\)[[:space:]]*=.*$/\1=${subvalue}/" "${CONFIG_TXT}";
				return;
			fi
		else
			if grep -q "^\s*${key}\s*=" ${CONFIG_TXT}; then
				sed -i "" -e "s/^\([[:space:]]*${key}[[:space:]]*=[[:space:]]*\).*$/\1${value}/" "${CONFIG_TXT}";
				return
			elif grep -q "^\s*#\s*${key}\s*=\s*.*$" "${CONFIG_TXT}"; then
				sed -i "" -e "s/^[[:space:]]*#[[:space:]]*\(${key}[[:space:]]*=[[:space:]]*\).*$/\1${value}/" "${CONFIG_TXT}";
				return
			fi
		fi

		if [ -z "${subvalue}" ]; then
			echo "${key}=${value}" >> "${CONFIG_TXT}";
		else
			echo "${key}=${value}=${subvalue}" >> "${CONFIG_TXT}";
		fi
	fi
}

enable_uart_serial_tty ()
{
	local CMDLINE_TXT="${BOOT}/cmdline.txt"
	local SERIAL_GETTY_AMA0_SERVICE="${ROOT}/etc/systemd/system/getty.target.wants/serial-getty@ttyAMA0.service"
	local UART_BAUDRATE=115200

	echo "Enabling UART and hardware serial tty..."

	if grep -q "console=serial0" "${CMDLINE_TXT}"; then
		sed -i "" -e 's/console=serial0,[0-9][0-9]* /console=ttyAMA0,'"${UART_BAUDRATE}"' /' "${CMDLINE_TXT}";
	elif ! grep -q "console=ttyAMA0" ${CMDLINE_TXT}; then
		sed -i "" -e 's/root=/console=ttyAMA0,'"${UART_BAUDRATE}"' root=/' "${CMDLINE_TXT}";
	elif ! grep -q "console=ttyAMA0,${UART_BAUDRATE} " ${CMDLINE_TXT}; then
		sed -i "" -e 's/\(console=ttyAMA0,\)[0-9][0-9]* /\1'"${UART_BAUDRATE}"' /' "${CMDLINE_TXT}";
	fi

	modify_config_value "enable_uart" "1"
	modify_config_value "dtoverlay"   "pi3-disable-bt"

	cat > ${SERIAL_GETTY_AMA0_SERVICE} <<-EOF
		[Unit]
		Description=Serial Getty on %I
		Documentation=man:agetty(8) man:systemd-getty-generator(8)
		Documentation=http://0pointer.de/blog/projects/serial-console.html
		BindsTo=dev-%i.device
		After=dev-%i.device systemd-user-sessions.service plymouth-quit-wait.service
		After=rc-local.service
		Before=getty.target
		IgnoreOnIsolate=yes

		[Service]
		ExecStart=-/sbin/agetty --autologin ${AUTOLOGIN_USER} --keep-baud 115200,38400,9600 %I \$TERM
		Type=idle
		Restart=always
		UtmpIdentifier=%I
		TTYPath=/dev/%I
		TTYReset=yes
		TTYVHangup=yes
		KillMode=process
		IgnoreSIGPIPE=no
		SendSIGHUP=yes

		[Install]
		WantedBy=getty.target
	EOF
}

enable_usb_serial_tty ()
{
	local SERIAL_GETTY_USB0_SERVICE="${ROOT}/etc/systemd/system/getty.target.wants/serial-getty@ttyUSB0.service"
	local UDEV_TTYUSB0_RULES="${ROOT}/etc/udev/rules.d/98-ttyusb0.rules"
	local USB_SERIAL_BAUDRATE="9600"

	echo "Enabling USB serial tty..."

	cat > ${SERIAL_GETTY_USB0_SERVICE} <<-EOF
		[Unit]
		Description=USB Serial Getty on %I
		BindsTo=dev-%i.device
		After=dev-%i.device systemd-user-sessions.service plymouth-quit-wait.service
		After=rc-local.service
		Before=getty.target
		IgnoreOnIsolate=yes

		[Service]
		ExecStart=-/sbin/agetty --autologin ${AUTOLOGIN_USER} --keep-baud ${USB_SERIAL_BAUDRATE} %I \$TERM
		Type=idle
		Restart=always
		UtmpIdentifier=%I
		TTYPath=/dev/%I
		TTYReset=yes
		TTYVHangup=yes
		KillMode=process
		IgnoreSIGPIPE=no
		SendSIGHUP=yes

		[Install]
		WantedBy=getty.target
	EOF

	cat > ${UDEV_TTYUSB0_RULES} <<-EOF
		KERNEL=="ttyUSB0", ENV{SYSTEMD_WANTS}="serial-getty@ttyUSB0.service"
	EOF
}

enable_console_auto_login ()
{
	local AUTOLOGIN_SERVICE="${ROOT}/etc/systemd/system/autologin@.service"
	local GETTY_SERVICE="${ROOT}/lib/systemd/system/getty@.service"
	local GETTY_TARGET_WANTS="${ROOT}/etc/systemd/system/getty.target.wants/getty@tty1.service"
	local LIGHTDM_CONF="${ROOT}/etc/lightdm/lightdm.conf"

	echo "Enabling console auto-login..."

	if ! grep -q "^ExecStart=-/sbin/agetty --autologin ${AUTOLOGIN_USER} " "${AUTOLOGIN_SERVICE}"; then
		sed -i "" -e 's,^ExecStart=-/sbin/agetty --autologin [^\s]*,ExecStart=-/sbin/agetty --autologin '"${AUTOLOGIN_USER}"','  "${AUTOLOGIN_SERVICE}"
	fi
	if [ ! -e "${GETTY_TARGET_WANTS}" ] || ! grep -q "^ExecStart=-/sbin/agetty --autologin ${AUTOLOGIN_USER} " "${GETTY_TARGET_WANTS}"; then
		rm -f "${GETTY_TARGET_WANTS}"
		cp -af "${AUTOLOGIN_SERVICE}" "${GETTY_TARGET_WANTS}"
	fi
	if ! grep -q "^ExecStart=-/sbin/agetty --autologin ${AUTOLOGIN_USER} " "${GETTY_SERVICE}"; then
		sed -i "" -e 's,^ExecStart=-/sbin/agetty --autologin [^\s]*,ExecStart=-/sbin/agetty --autologin '"${AUTOLOGIN_USER}"','  "${GETTY_SERVICE}"
		sed -i "" -e 's,^ExecStart=-/sbin/agetty --noclear,ExecStart=-/sbin/agetty --autologin '"${AUTOLOGIN_USER}"' --noclear,' "${GETTY_SERVICE}"
	fi

	if ! grep -q "autologin-user=${AUTOLOGIN_USER}\s*$" "${LIGHTDM_CONF}"; then
		sed -i "" -e 's/^#*\(autologin-user=\).*$/\1'"${AUTOLOGIN_USER}"'/' "${LIGHTDM_CONF}"
	fi
}

enable_usb_internet_sharing ()
{
	local INTERFACES_D="${ROOT}/etc/network/interfaces.d"
	local IFUP_D="${ROOT}/etc/network/if-up.d"
	local IFDOWN_D="${ROOT}/etc/network/if-down.d"
	local SYSTEMD="${ROOT}/lib/systemd/system/multi-user.target.wants"
	local DOT_BASHRC="${ROOT}/home/pi/.bashrc"

	echo "Enabling USB Internet Sharing..."

	cat > ${INTERFACES_D}/usb0 <<-EOF
	allow-hotplug usb0
	iface usb0 inet dhcp
	EOF

	cat > ${SYSTEMD}/usb_remote_tty.service <<-EOF
	[Unit]
	Description=Rescue Remote TTY
	After=network.target

	[Service]
	ExecStart=/usr/bin/socat tcp-listen:23,bind=192.168.42.1,reuseaddr,fork exec:"/bin/login -f pi",pty,stderr,setsid,sigint,sane
	ExecReload=/bin/kill -HUP \$MAINPID
	Restart=on-failure
	KillMode=process

	[Install]
	WantedBy=multi-user.target
	EOF

	cat > "${IFUP_D}/usb_remote_tty" <<-EOF
	#!/bin/sh
	[ ! "\${IFACE}" = "usb0" ] && exit 0;
	[ ! "\${ADDRFAM}" = "inet" ] && [ ! "\$ADDRFAM" = "inet6" ] && exit 0;
	case "\${MODE}" in
	    start) ACTION=restart;
	           ifconfig \${IFACE}:1 inet 192.168.42.1 netmask 255.255.255.0;
	           ifconfig \${IFACE}:2 inet 172.20.10.10 netmask 255.255.255.240; ;;
	    stop)  ACTION=stop;
	           ifconfig \${IFACE}:1 inet 0.0.0.0 down;
	           ifconfig \${IFACE}:2 inet 0.0.0.0 down; ;;
	    *)     exit 0; ;;
	esac
	if [ -d /run/systemd/system ]; then
	    systemctl \${ACTION} usb_remote_tty >/dev/null 2>&1 || true
	else
	    invoke-rc.d usb_remote_tty \${ACTION} >/dev/null 2>&1 || true
	fi
	exit 0;
	EOF

	chmod a+x ${IFUP_D}/usb_remote_tty
	ln -sf /etc/network/if-up.d/usb_remote_tty ${IFDOWN_D}/usb_remote_tty

	if egrep -q '^\s*#\s*echo\s+-n\s+"@ipaddr="\s*;\s*hostname\s+-I' "${DOT_BASHRC}"; then
		sed -i "" -e 's/^[[:space:]]*#[[:space:]]*\(echo [[:space:]]*-n [[:space:]]*"@ipaddr="[[:space:]]*;[[:space:]]*hostname [[:space:]]*-I.*\)$/\1/' "${DOT_BASHRC}"
	elif ! egrep -q '^\s*echo\s+-n\s+"@ipaddr="\s*;\s*hostname\s+-I' "${DOT_BASHRC}"; then
		echo 'echo -n "@ipaddr=";hostname -I' >> "${DOT_BASHRC}"
	fi
}

enable_network_interfaces ()
{
	INTERFACES_D="${ROOT}/etc/network/interfaces.d"
	WPA_SUPPLICANT_CONF="${ROOT}/etc/wpa_supplicant/wpa_supplicant.conf"

	cat > "${INTERFACES_D}/eth0" <<-EOF
	auto eth0
	iface eth0 inet dhcp
	EOF

	cat > "${INTERFACES_D}/wlan0" <<-EOF
	auto wlan0
	iface wlan0 inet dhcp
	       wpa_conf /etc/wpa_supplicant/wpa_supplicant.conf
	EOF

	cat > "${WPA_SUPPLICANT_CONF}" <<-EOF
	country=JP
	ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
	update_config=1
	EOF
}

enable_i2c_interface ()
{
	local RASPI_BLACKLIST_CONF="${ROOT}/etc/modprobe.d/raspi-blacklist.conf"
	local MODULES="${ROOT}/etc/modules"

	sed -i "" -e "s/^\(blacklist[[:space:]]*i2c[-_]bcm2708\)/#\1/" "${RASPI_BLACKLIST_CONF}"
	sed -i "" -e "s/^#[[:space:]]*\(i2c[-_]dev\)/\1/" "${MODULES}"
	if ! grep -q "^i2c[-_]dev" "${MODULES}"; then
		echo "i2c-dev" >> "${MODULES}"
	fi

	modify_config_value "dtparam" "i2c_arm" "on"
}

disable_undervoltage_detection ()
{
	#avoid_warnings=1 disables the warning overlays.
	#avoid_warnings=2 disables the warning overlays, but additionally allows turbo mode even when low-voltage is present.
	modify_config_value "avoid_warnings" "1"
}

#START_OF_HOSTNAME_PASSWORD_CHANGING_SCRIPT
change_hostname_password ()
{
	local IDENTITY_TXT="/boot/identity.txt"
	local DOT_BASHRC="/home/pi/.bashrc"
	local cur_macaddr="$(ip link show eth0 | awk '$1 ~ /ether/{print $2}')"

	if [ -f "${IDENTITY_TXT}" ]; then
		last_macaddr="$(cat "${IDENTITY_TXT}" | awk -F= '$1 ~ /@macaddr/ {print $2}')"

		if [ "${cur_macaddr}" = "${last_macaddr}" ]; then
			return;
		fi
		rm -f "${IDENTITY_TXT}";
	fi

	local HOSTNAME="trendcar-$(ip link show eth0 | awk '$1 ~ /ether/{print $2}' | md5sum | awk '{print substr($1, 1, 6)}')";
	echo "${HOSTNAME}" > /etc/hostname
	sed -i -e 's/^\(\s*127.0.1.1\s\+\).*$/\1'"${HOSTNAME}"'/' /etc/hosts
	hostname -b localhost
	hostname -b "${HOSTNAME}"
	echo "@hostname=${HOSTNAME}" >> "${IDENTITY_TXT}"

	local password="$(dd if=/dev/random count=1 2>/dev/null| md5sum | awk '{printf("%s", substr($1, 1, 8))}')";
	echo "pi:${password}" | chpasswd
	echo "@passwd=${password}" >> "${IDENTITY_TXT}"

	if egrep -q '^\s*#\s*cat\s+'"${IDENTITY_TXT}" "${DOT_BASHRC}"; then
		sed -i -e 's,^\s*#\s*\(cat\s\+'"${IDENTITY_TXT}"'.*\)$,\1,' "${DOT_BASHRC}";
	elif ! egrep -q '^\s*cat\s+'"${IDENTITY_TXT}" "${DOT_BASHRC}"; then
		echo 'cat '"${IDENTITY_TXT}" >> "${DOT_BASHRC}";
	fi

	echo "@macaddr=${cur_macaddr}" >> "${IDENTITY_TXT}"
}
#END_OF_HOSTNAME_PASSWORD_CHANGING_SCRIPT

embed_script_for_changing_hostname_password ()
{
	local RC_LOCAL="${ROOT}/etc/rc.local"
	local START_TAG="START_OF_HOSTNAME_PASSWORD_CHANGING_SCRIPT"
	local END_TAG="END_OF_HOSTNAME_PASSWORD_CHANGING_SCRIPT"

	echo "Embedding script for changing hostname and password per RPi"

	sed -i "" -e '/^[[:space:]]*\#[[:space:]]*'"${START_TAG}"'.*$/,/^[[:space:]]*\#[[:space:]]*'"${END_TAG}"'.*$/d' \
	          -e 's/^[[:space:]]*exit[[:space:]]*[0-9]*/#&/' "${RC_LOCAL}"

	cat "${SCRIPT_SELF}" | \
	sed -n -e '/^[[:space:]]*#[[:space:]]*'"${START_TAG}"'.*$/,/^[[:space:]]*#[[:space:]]*'"${END_TAG}"'.*$/p' | \
	sed -e 's/^[[:space:]]*\#[[:space:]]*'"${END_TAG}"'.*$/change_hostname_password;/' >> "${RC_LOCAL}"
	echo "#${END_TAG}" >> "${RC_LOCAL}"
}

install_trendcar ()
{
	local INSTALL_BASEDIR="${ROOT}/opt/trendcar"
	local TRENDCAR_SERVICE="${ROOT}/lib/systemd/system/trendcar.service"

	echo "Installing Trend Car programs..."

	mkdir -p "${INSTALL_BASEDIR}"
	rm -rf "${INSTALL_BASEDIR}/bin"
	cp -af "${SOURCE_BASEDIR}/bin" "${INSTALL_BASEDIR}/"

	find "${INSTALL_BASEDIR}" -type f -name "*.sh" | xargs chmod a+x
	for script in "trendcar-config" \
		      "trendcar-daemon" \
		      "trendcar-ini"    \
		      "trendcar-cli"    \
		      "trendcar-console"; do

		chmod a+x "${INSTALL_BASEDIR}/bin/${script}";
		ln -sf "/opt/trendcar/bin/${script}" "${ROOT}/usr/bin/${script}";
	done

	rm -rf "${INSTALL_BASEDIR}/trendcar"
	cp -af "${SOURCE_BASEDIR}/trendcar" "${INSTALL_BASEDIR}/"
	find "${INSTALL_BASEDIR}/trendcar" \( -name "*.pyc" -or -name "*.orig" -or -name "*.new" -or -name "*.bak" -or -name "*.test" -or -name ".*.sw?" \) -exec rm -f {} \;
	sed -i '' -e 's/^\([[:space:]]*release_date[[:space:]]*=[[:space:]]*\).*$/\1'"$(date "+%b %d, %Y")"'/' "mnt/root/opt/trendcar/trendcar/config.ini"

	rm -rf "${INSTALL_BASEDIR}/extra"
	cp -af "${SOURCE_BASEDIR}/extra" "${INSTALL_BASEDIR}/"
	cp -af "${SOURCE_BASEDIR}/LICENSE" "${INSTALL_BASEDIR}/"

	chown -R 1000 "${INSTALL_BASEDIR}"
	chgrp -R 1000 "${INSTALL_BASEDIR}"

	cat > "${TRENDCAR_SERVICE}" <<-EOF
	[Unit]
	Description=Trend Car Driver Service
	After=network.target

	[Service]
	ExecStart=/usr/bin/trendcar-daemon
	ExecReload=/bin/kill -HUP \$MAINPID
	ExecStop=/bin/kill -HUP \$MAINPID
	Restart=on-failure
	KillMode=process

	[Install]
	WantedBy=multi-user.target
	Alias=trendcar.service
	EOF
}

inject_post_config_at_boot ()
{
	local rootfs_init_size="$1"
	local CMDLINE_TXT="${BOOT}/cmdline.txt"
	local INIT_CONFIG_SH="/usr/lib/raspi-config/init_config.sh"
	local RESIZE2FS_ONCE_SH="/usr/lib/raspi-config/resize2fs_once.sh"
	local RESIZE2FS_ONCE_SERVICE="/lib/systemd/system/resize2fs_once.service"

	echo "Injecting post configuration for the first boot..."

	if [ -z "${rootfs_init_size}" ]; then
		rm -f "${BOOT}/rootfs_init_size"
	else
		echo "${rootfs_init_size}" > "${BOOT}/rootfs_init_size"
	fi

	cat > "${ROOT}/${INIT_CONFIG_SH}" <<-EOF
	#!/bin/sh
	export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin

	mount -t proc proc /proc
	mount -t sysfs sys /sys
	mount -t tmpfs tmp /run
	mkdir -p /run/systemd

	mount /boot
	mount / -o remount,rw

	sed -i -e 's# init=[^ ]* # #' /boot/cmdline.txt

	systemctl set-default multi-user.target
	systemctl enable serial-getty@ttyUSB0.service
	systemctl enable serial-getty@ttyAMA0.service
	systemctl enable usb_remote_tty.service
	systemctl stop hciuart
	systemctl disable hciuart

	systemctl enable ssh
	systemctl enable trendcar
	systemctl enable resize2fs_once

	sync; sync; sync
	echo 3 > /proc/sys/vm/drop_caches
	umount /boot
	mount / -o remount,ro

	echo b > /proc/sysrq-trigger
	sleep 5
	exit 0
	EOF
	chmod a+x "${ROOT}/${INIT_CONFIG_SH}"
	if grep -q " init=" "${CMDLINE_TXT}"; then
		sed -i "" -e 's| init=[^ ]* | init='"${INIT_CONFIG_SH}"' |' "${CMDLINE_TXT}"
	else
		sed -i "" -e 's| quiet  *splash | quiet init='"${INIT_CONFIG_SH}"' splash |' "${CMDLINE_TXT}"
	fi

	cat > "${ROOT}/${RESIZE2FS_ONCE_SERVICE}" <<-EOF
	[Unit]
	Description=Resize the root file system to its maximum size
	Before=display-manager.service getty.target autologin@tty1.service

	[Service]
	Type=oneshot
	TimeoutSec=600
	ExecStart=${RESIZE2FS_ONCE_SH}
	ExecStartPost=/bin/systemctl disable resize2fs_once

	[Install]
	WantedBy=sysinit.target
	EOF

	cat > "${ROOT}/${RESIZE2FS_ONCE_SH}" <<-EOF
	#!/bin/sh
	export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin

	root_part_dev="\$(findmnt / -o source -n)"
	root_part_name="\${root_part_dev##*/}"
	root_dev_name="\$(echo /sys/block/*/"\${root_part_name}" | cut -d / -f 4)"
	root_dev="/dev/\${root_dev_name}"
	root_part_num="\$(cat "/sys/block/\${root_dev_name}/\${root_part_name}/partition")"

	if [ -r "/boot/rootfs_init_size" ]; then
	    new_size="\$(cat /boot/rootfs_init_size)";
	    new_part_end="\$(parted -m "\${root_dev}" unit s print | awk -F: -v new_size="\${new_size}" -v part="\${root_part_num}" '
	    \$1 == part {
	        cur_end  = int(\$3)
	        cur_size = int(\$4)
	        new_end  = cur_end + ((new_size / 512) - cur_size)
	        print new_end
	        exit 0
	    }')"
	else
	    new_part_end="\$(( \$(cat /sys/block/\${root_dev_name}/size) - 1 ))";
	fi

	old_disk_id="\$(fdisk -l "\${root_dev}" | sed -n 's/Disk identifier: 0x\([^ ]*\)/\1/p')"

	if parted -m "\${root_dev}" unit s resizepart "\${root_part_num}" "\${new_part_end}"; then
	    new_disk_id="\$(fdisk -l "\${root_dev}" | sed -n 's/Disk identifier: 0x\([^ ]*\)/\1/p')"
	    sed -i -e "s/\${old_disk_id}/\${new_disk_id}/g" /etc/fstab
	    sed -i -e "s/\${old_disk_id}/\${new_disk_id}/g" /boot/cmdline.txt
	    partprobe "\${root_dev}"
	fi

	resize2fs "\${root_part_dev}"

	sync; sync; sync
	echo 3 > /proc/sys/vm/drop_caches
	EOF
	chmod a+x "${ROOT}/${RESIZE2FS_ONCE_SH}"
}

cleanup ()
{
	local PI_DOT_BASH_HISTORY="${ROOT}/home/pi/.bash_history"
	local ROOT_DOT_BASH_HISTORY="${ROOT}/root/.bash_history"

	for history in "${PI_DOT_BASH_HISTORY}" "${ROOT_DOT_BASH_HISTORY}"; do
		if [ -e "${history}" ]; then
			echo > "${history}"
		fi
	done

	for dir in ${BOOT} ${ROOT}; do
		if [ -e ${dir}/.fseventsd ]; then
			rm -rf ${dir}/.fseventsd
		fi
	done

	rm -rf "${ROOT}/home/pi/.cache/*"
	rm -rf "${ROOT}/home/pi/trendcar"

	for logfile in auth.log daemon.log lastlog syslog wtmp; do
		rm -f "${ROOT}/var/log/${logfile}"
	done

	rm -f "${BOOT}/identity.txt"
	echo "raspberry" > "${ROOT}/etc/hostname"
	sed -i "" -e 's/^\([[:space:]]*127.0.1.1[[:space:]][[:space:]]*\).*$/\1raspberry/' "${ROOT}/etc/hosts"
	sed -i "" -e '/^[[:space:]]*#?[[:space:]]*cat[[:space:]][[:space:]]*\/boot\/identity\.txt/d' "${ROOT}/home/pi/.bashrc"

	local VAR_LOG="${ROOT}/var/log"

	find "${VAR_LOG}" | while read log_file; do
		case "${log_file}" in
			${ROOT}/var/log      |\
			${ROOT}/var/log/apt  |\
			${ROOT}/var/log/samba)
				continue;
			;;
			${ROOT}/var/log/apt/eipp.log.xz |\
			${ROOT}/var/log/apt/history.log |\
			${ROOT}/var/log/apt/term.log    |\
			${ROOT}/var/log/dpkg.log        |\
			${ROOT}/var/log/btmp            |\
			${ROOT}/var/log/alternatives.log|\
			${ROOT}/var/log/bootstrap.log   |\
			${ROOT}/var/log/fontconfig.log  |\
			${ROOT}/var/log/faillog         )
				> "${log_file}";
			;;
			*)
				rm -rf "${log_file}";
			;;
		esac
	done

#	TODO:
#	git init
#	cat > .gitigore <<-EOF
#	/dev
#	/proc
#	/sys
#	/run
#	/var/run
#	/tmp
#	/var/tmp
#	EOF
#	git add .gitignore bin boot etc home lib opt root sbin usr var
}

modify_sd_settings ()
{
	enable_uart_serial_tty
	enable_usb_serial_tty
	enable_console_auto_login
	enable_usb_internet_sharing
	enable_network_interfaces
	enable_i2c_interface
	disable_undervoltage_detection
	embed_script_for_changing_hostname_password
	install_trendcar
	if [ ${PUBLISH} -ne 0 ]; then
		inject_post_config_at_boot
	else
		inject_post_config_at_boot 8053063680	# 7.5 * 1024 * 1024 * 1024

	fi
	cleanup
}

if [ ${MOUNT_ONLY} -ne 0 ]; then
	mount_sd_partitions
	exit 0;
fi

extract_image_to_sd
mount_sd_partitions
modify_sd_settings
exit 0;
