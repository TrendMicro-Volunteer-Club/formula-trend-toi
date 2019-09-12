#!/bin/sh

_realpath () {
	hash realpath >/dev/null 2>&1 && realpath "$1" && return;
	[ -L "$1" ] && readlink "$1" && return;
	echo "$1"
}
export TRENDCAR_HOME=$(cd $(dirname $(_realpath $0))/..; pwd)

get_python_preference ()
{
	local python_preference="2.7"

	for ini in ~pi/trendcar/userconfig.ini \
	           "${TRENDCAR_HOME}/trendcar/config.ini" ]; do

		if [ -r "${ini}" ]; then
			python_preference="$(
				awk -F= '
				$1 ~ /^[ \t]*python_preference[ \t]*$/ {
					sub(/^[ \t]+/, "", $2);
					sub(/[ \t]+$/, "", $2);
					printf("%s", $2);
					exit(0)
				}
				' "${ini}"
			)";

			if [ ! -z "${python_preference}" ]; then
				break
			fi
		fi
	done

	echo "${python_preference}"
}

get_python_path_for_opencv ()
{
	local python_preference="$(get_python_preference)"
	local opencv_lib_path="$(cat /etc/ld.so.conf.d/opencv.conf)"

	case "${python_preference}" in
		2.7-cv3)	echo -n ":${opencv_lib_path}/python2.7"; ;;
		3.5-cv3)	echo -n ":${opencv_lib_path}/python3.5"; ;;
	esac
}
export PYTHONPATH="${TRENDCAR_HOME}/trendcar$(get_python_path_for_opencv):${PYTHONPATH}"

find_python ()
{
	local python_preference="$(get_python_preference)"

	case "${python_preference}" in
		3*) local python_list="python python3"  ; python_ver_regexp='^Python[ \t]\+3\.'    ;;
		 *) local python_list="python python2.7"; python_ver_regexp='^Python[ \t]\+2\.7\.' ;;
	esac

	for py in ${python_list}; do
		local python_exec="$(which "${py}")"

		if [ -z "${python_exec}" ]; then
			continue;
		fi

		if "${python_exec}" --version 2>&1 | grep -i -q "${python_ver_regexp}"; then
			echo "${python_exec}";
			return;
		fi
	done
	echo "python"
}

write_trendcar_pid ()
{
	local pid="$1"

	echo "TrendCar (pid: ${pid}) is running..."
	sudo sh -c "echo -n \"${pid}\" > /var/run/trendcar.pid"
	return $?
}

wait_trendcar_pid ()
{
	while true; do
		local pid="$(cat /var/run/trendcar.pid 2>/dev/null)"
		if [ -z "${pid}" ]; then
			echo "trendcar-daemon exited"
			break
		fi
		if [ ! -d "/proc/${pid}" ]; then
			echo "trendcar-daemon exited abnormally"
			sleep 1;
			break;
		fi
		wait ${pid}
	done
}

terminate_trendcar ()
{
	while true; do
		local pid="$(cat /var/run/trendcar.pid 2>/dev/null)";
		if [ -z "${pid}" ]; then
			break
		fi
		if [ ! -d "/proc/${pid}" ]; then
			break;
		fi
		sudo kill -INT "${pid}" >/dev/null 2>&1
		sleep 1

		if [ ! -d "/proc/${pid}" ]; then
			break;
		fi
		sudo kill "${pid}" >/dev/null 2>&1
		echo "Waiting TrendCar (pid: ${pid}) to stop..."
	done
	sudo rm -f /var/run/trendcar.pid
}

fix_udev_mounts ()
{
	if egrep -q '^\s*MountFlags\s*=\s*slave\s*.*$' /lib/systemd/system/systemd-udevd.service; then
		sed -i -e 's/^\(\s*MountFlags\s*=\s*\)slave\(\s*.*\)$/\1shared\2/' /lib/systemd/system/systemd-udevd.service
	fi

	for proc_pid in $(find /proc -maxdepth 1 -name "[0-9]*" -type d); do
		if [ "$(readlink "${proc_pid}/exe")" = "/lib/systemd/systemd-udevd" ]; then
			if cat "${proc_pid}/mounts" | awk '$1 == "/dev/root" {if ($4 ~ /ro/) exit 0; else exit 1}'; then
				/etc/init.d/udev restart
			fi
			break;
		fi
	done
}

running_in_pi ()
{
    test -e "/sys/firmware/devicetree/base/model"
}

PYTHON=${PYTHON-$(find_python)}

