#!/bin/sh

OPENCV_VER=3.4.3

prepare ()
{
	local name="$1"
	local ver="$2"
	local filename="${name}-${ver}.zip"

	if [ ! -f "${filename}" ]; then
		wget -t 0 -c "https://github.com/opencv/${name}/archive/${ver}.zip" -O "${filename}"
	fi

	if [ ! -d "${name}-${ver}" ]; then
		unzip "${filename}"
	fi
}

build_opencv ()
{
	local build_dir="$(pwd)/opencv-${OPENCV_VER}/build"
	local opencv_contrib_dir="$(pwd)/opencv_contrib-${OPENCV_VER}"

	sudo sed -i -e 's/^\(CONF_SWAPSIZE=\).*$/\11024/' /etc/dphys-swapfile
	sudo /etc/init.d/dphys-swapfile stop
	sudo /etc/init.d/dphys-swapfile start
	
	rm -rf "${build_dir}"
	(mkdir -p "${build_dir}" && cd "${build_dir}" && \
	cmake -DCMAKE_BUILD_TYPE=RELEASE \
	      -DBUILD_EXAMPLES=OFF \
	      -DINSTALL_PYTHON_EXAMPLES=OFF \
	      -DOPENCV_EXTRA_MODULES_PATH=${opencv_contrib_dir}/modules .. && \
        make -j 4)

	sudo sed -i -e 's/^\(CONF_SWAPSIZE=\).*$/\1100/' /etc/dphys-swapfile
	sudo /etc/init.d/dphys-swapfile stop
	sudo /etc/init.d/dphys-swapfile start
}

package_opencv ()
{
	local target_name="opencv"
	local build_dir="$(pwd)/opencv-${OPENCV_VER}/build"
	local dist_dir="$(pwd)/dist"
	local package="python-opencv-${OPENCV_VER}.tgz"

	rm -rf "${dist_dir}"
	mkdir -p "${dist_dir}"
	cp -af "${build_dir}/lib" "${dist_dir}/${target_name}"
	mkdir -p "${dist_dir}/${target_name}/python2.7"
	mv -f "${dist_dir}/${target_name}/cv2.so" "${dist_dir}/${target_name}/python2.7/"
	mv -f "${dist_dir}/${target_name}/python3" "${dist_dir}/${target_name}/python3.5"
	echo "${OPENCV_VER}" > "${dist_dir}/${target_name}/VERSION"
	tar -C "${dist_dir}" -czf "${package}" "${target_name}"
}

prepare "opencv"         "${OPENCV_VER}"
prepare "opencv_contrib" "${OPENCV_VER}"
build_opencv
package_opencv

