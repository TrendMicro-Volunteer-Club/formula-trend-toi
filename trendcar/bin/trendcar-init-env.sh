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
# Update firmware
rpi-update

# Update APT index
apt-get update

# Default choices for iptables-persistent installation
echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections

# Additional apps
apt-get install -y screen tmux socat iptables-persistent x11vnc vim usbmount unrar-free p7zip-full unzip lsof strace atop

#####################################################################
PIP_TRUSTED_HOSTS="--trusted-host pypi.python.org --trusted-host pypi.org --trusted-host files.pythonhosted.org"

#####################################################################
# Update python 2 modules
pip install ${PIP_TRUSTED_HOSTS} --upgrade pip
apt-get install -y python-dbg libpython-dbg python-opencv python-smbus python-virtualenv
apt-get install -y python2.7-dev python-numpy python-scipy python-matplotlib python-pil python-h5py python-sklearn python-skimage python-pandas python-sklearn-pandas
apt-get install -y cython cython-dbg
pip install ${PIP_TRUSTED_HOSTS} numpy-indexed
pip install ${PIP_TRUSTED_HOSTS} pytesseract
#pip install --ignore-installed tensorflow
pip install ${PIP_TRUSTED_HOSTS} --upgrade tensorflow
pip install ${PIP_TRUSTED_HOSTS} keras

# movidius
apt-get install -y --no-install-recommends libboost-all-dev
apt-get install -y coreutils libleveldb-dev libsnappy-dev libopencv-dev libhdf5-serial-dev libgraphviz-dev
apt-get install -y libgflags-dev libgoogle-glog-dev liblmdb-dev swig3.0 libxslt-dev libxml2-dev

apt-get install -y python-protobuf libprotobuf-dev protobuf-compiler python-markdown python-yaml python-nose python-tk
pip install ${PIP_TRUSTED_HOSTS} Cython graphviz pygraphviz Enum34 networkx

# Update python 3 modules
apt-get install -y build-essential cmake pkg-config
apt-get install -y libjpeg-dev libtiff5-dev libjasper-dev libpng12-dev
apt-get install -y libavcodec-dev libavformat-dev libswscale-dev libv4l-dev v4l-utils
apt-get install -y libxvidcore-dev libx264-dev libgstreamer0.10-0-dbg libgstreamer0.10-0 libgstreamer0.10-dev 
apt-get install -y libgtk2.0-dev libgtk-3-dev libgtkglext1-dev libqtgui4 libqt4-test
apt-get install -y libatlas-base-dev gfortran cython3 cython3-dbg

apt-get install -y python3 python3-dbg libpython3-dbg python3-setuptools python3-pip python3-virtualenv
apt-get install -y python3.5-dev python3-numpy python3-scipy python3-matplotlib python3-pil python3-h5py python3-sklearn python3-skimage python3-pandas python3-sklearn-pandas
pip3 install ${PIP_TRUSTED_HOSTS} --upgrade pip3
pip3 install ${PIP_TRUSTED_HOSTS} opencv-python opencv-contrib-python numpy-indexed
pip3 install ${PIP_TRUSTED_HOSTS} pytesseract
#pip3 install ${PIP_TRUSTED_HOSTS} --ignore-installed tensorflow
pip3 install ${PIP_TRUSTED_HOSTS} --upgrade tensorflow
pip3 install ${PIP_TRUSTED_HOSTS} keras

# movidius
apt-get install -y python3-protobuf python3-markdown python3-yaml python3-nose python3-tk
pip3 install ${PIP_TRUSTED_HOSTS} Cython graphviz pygraphviz Enum34 networkx

#####################################################################
# Update Movidius NCSDK
NCSDK_BASEDIR="/tmp/ncsdk"
NCSDK_URL="$(curl https://movidius.github.io/ncsdk/install.html 2>/dev/null | awk '
	/<code>wget +https:/ {
		sub(/^.*<code>wget +/, "");
		sub(/ *<br>.*$/, "");
		print;
		exit;
	}
')"

if [ -z "${NCSDK_URL}" ]; then
	NCSDK_URL="https://ncs-forum-uploads.s3.amazonaws.com/ncsdk/ncsdk-02_05_00_02-full/ncsdk-2.05.00.02.tar.gz";
fi

mkdir -p "${NCSDK_BASEDIR}"

NCSDK_CHKSUM="/ncsdk.sha256"
NCSDK_FILENAME="${NCSDK_BASEDIR}/$(basename "${NCSDK_URL}")"
NCSDK_TEMP_FILENAME="${NCSDK_FILENAME}.tmp"
NCSDK_FOLDER="${NCSDK_BASEDIR}/$(basename -s .tar.gz "${NCSDK_URL}")"

rm -f "${NCSDK_FILENAME}"

for folder in $(find "${NCSDK_BASEDIR}" -maxdepth 1 -type d -name "ncsdk-*"); do
	#make -C "${folder}" uninstall;
	rm -rf "${folder}";
done

if wget -O "${NCSDK_FILENAME}" -c -t 60 -w 1 --random-wait "${NCSDK_URL}"; then
	if tar -tzf "${NCSDK_FILENAME}"; then
		if [ -f "${NCSDK_CHKSUM}" ] && [ -e /usr/local/include/mvnc.h ] && python -c "import mvnc.mvncapi"; then
			chksum1="$(cat "${NCSDK_CHKSUM}")"
			chksum2="$(sha256sum "${NCSDK_FILENAME}" | awk '{print $1}')"

			if [ "${chksum1}" = "${chksum2}" ]; then
				rm -f "${NCSDK_FILENAME}"
			fi
		fi
	else
		rm -f "${NCSDK_FILENAME}"
	fi
fi

if [ -f "${NCSDK_FILENAME}" ]; then
	if tar -C "${NCSDK_BASEDIR}" -xzf "${NCSDK_FILENAME}"; then
		apt-get install -y libusb-1.0-0-dev libusb-1.0.0
		cd "${NCSDK_FOLDER}"; make api && (sha256sum "${NCSDK_FILENAME}" | awk '{print $1}' > "${NCSDK_CHKSUM}")
		ADDITIONAL_NCSDK_URL="$(cat "${NCSDK_FOLDER}/install.sh" | sed -n -e '/http.*NCSDK-.*\.tar\.gz/s/^[^"]*"\([^"]*\)"/\1/p')"
		rm -rf "${NCSDK_FOLDER}"
	fi
fi

ADDITIONAL_NCSDK_CHKSUM="/NCSDK.sha256"
ADDITIONAL_NCSDK_FILENAME="${NCSDK_BASEDIR}/$(basename "${ADDITIONAL_NCSDK_URL}")"
ADDITIONAL_NCSDK_TEMP_FILENAME="${ADDITIONAL_NCSDK_FILENAME}.tmp"
ADDITIONAL_NCSDK_FOLDER="${NCSDK_BASEDIR}/$(basename -s .tar.gz "${ADDITIONAL_NCSDK_URL}")"

if [ -z "${ADDITIONAL_NCSDK_URL}" ]; then
	ADDITIONAL_NCSDK_URL="https://downloadmirror.intel.com/27839/eng/NCSDK-2.05.00.02.tar.gz"
fi

if wget -O "${ADDITIONAL_NCSDK_FILENAME}" -c -t 60 -w 1 --random-wait "${ADDITIONAL_NCSDK_URL}"; then
	if tar -tzf "${ADDITIONAL_NCSDK_FILENAME}"; then
		if [ -f "${ADDITIONAL_NCSDK_CHKSUM}" ]; then
			chksum1="$(cat "${ADDITIONAL_NCSDK_CHKSUM}")"
			chksum2="$(sha256sum "${ADDITIONAL_NCSDK_FILENAME}" | awk '{print $1}')"

			if [ "${chksum1}" = "${chksum2}" ]; then
				rm -f "${ADDITIONAL_NCSDK_FILENAME}"
			fi
		fi
	else
		rm -f "${ADDITIONAL_NCSDK_FILENAME}"
	fi
fi

if [ -f "${ADDITIONAL_NCSDK_FILENAME}" ]; then
	if tar -C "${NCSDK_BASEDIR}" -xzf "${ADDITIONAL_NCSDK_FILENAME}"; then
		(cd "${ADDITIONAL_NCSDK_FOLDER}/ncsdk-armv7l" &&
		 rm -rf /usr/bin/ncsdk &&
		 cp -r  tk /usr/bin/ncsdk &&
		 ln -sf /usr/bin/ncsdk/mvNCCompile.py /usr/bin/mvNCCompile &&
		 ln -sf /usr/bin/ncsdk/mvNCCheck.py   /usr/bin/mvNCCheck   &&
		 ln -sf /usr/bin/ncsdk/mvNCProfile.py /usr/bin/mvNCProfile) && \
		(sha256sum "${ADDITIONAL_NCSDK_FILENAME}" | awk '{print $1}' > "${ADDITIONAL_NCSDK_CHKSUM}")

		rm -rf "${ADDITIONAL_NCSDK_FOLDER}"

		#comment out "from .Caffe import CaffeParser"
		sed -i -e 's/^\s*from\s*.Caffe\s*import\s*CaffeParser\s*$/#&/' /usr/bin/ncsdk/Controllers/Parsers/__init__.py
		#comment out "from Controllers.Parsers.Caffe import CaffeParser"
		sed -i -e 's/^\s*from\s*Controllers.Parsers.Caffe\s*import\s*CaffeParser\s*$/#&/' /usr/bin/ncsdk/Controllers/Scheduler.py
	fi
fi

#####################################################################
sh /opt/trendcar/bin/trendcar-setup.sh

#####################################################################
# Complete the system upgrades (optional)
apt-get remove -y wolfram-engine
apt-get upgrade -y
#apt-get dist-upgrade -y

sync; sync; sync
echo 3 > /proc/sys/vm/drop_caches

