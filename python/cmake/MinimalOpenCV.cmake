# Provides a minimal, static OpenCV (core, imgproc, calib3d) for the python bindings.
#
# If CIMBAR_OPENCV_PREFIX (cache variable or environment variable) already holds an install,
# it is reused. Otherwise OpenCV is downloaded, built and installed there at configure time.
# CI points CIMBAR_OPENCV_PREFIX at a cached directory, so the slow build happens once per platform.

set(CIMBAR_OPENCV_VERSION "4.10.0")
set(CIMBAR_OPENCV_SHA256 "b2171af5be6b26f7a06b1229948bbb2bdaa74fcf5cd097e0af6378fce50a6eb9")

if(NOT CIMBAR_OPENCV_PREFIX AND DEFINED ENV{CIMBAR_OPENCV_PREFIX})
	set(CIMBAR_OPENCV_PREFIX "$ENV{CIMBAR_OPENCV_PREFIX}")
endif()
if(NOT CIMBAR_OPENCV_PREFIX)
	set(CIMBAR_OPENCV_PREFIX "${CMAKE_BINARY_DIR}/opencv-install")
endif()
file(TO_CMAKE_PATH "${CIMBAR_OPENCV_PREFIX}" CIMBAR_OPENCV_PREFIX)
# on Windows, OpenCVConfig.cmake only looks for static libs when asked to
set(OpenCV_STATIC ON)
set(CIMBAR_OPENCV_PREFIX "${CIMBAR_OPENCV_PREFIX}" CACHE PATH "Install prefix of the minimal static OpenCV" FORCE)

find_package(OpenCV ${CIMBAR_OPENCV_VERSION} EXACT QUIET CONFIG
	PATHS "${CIMBAR_OPENCV_PREFIX}" NO_DEFAULT_PATH)

if(NOT OpenCV_FOUND)
	set(_cv_work "${CMAKE_BINARY_DIR}/opencv")
	set(_cv_archive "${_cv_work}/opencv-${CIMBAR_OPENCV_VERSION}.tar.gz")
	set(_cv_src "${_cv_work}/opencv-${CIMBAR_OPENCV_VERSION}")
	set(_cv_build "${_cv_work}/build")

	if(NOT EXISTS "${_cv_src}/CMakeLists.txt")
		message(STATUS "Downloading OpenCV ${CIMBAR_OPENCV_VERSION}")
		file(DOWNLOAD
			"https://github.com/opencv/opencv/archive/refs/tags/${CIMBAR_OPENCV_VERSION}.tar.gz"
			"${_cv_archive}"
			EXPECTED_HASH SHA256=${CIMBAR_OPENCV_SHA256}
			TLS_VERIFY ON
		)
		file(ARCHIVE_EXTRACT INPUT "${_cv_archive}" DESTINATION "${_cv_work}")
	endif()

	# build with the same generator/compiler/architecture as the parent project
	set(_cv_args
		-G "${CMAKE_GENERATOR}"
		-DCMAKE_BUILD_TYPE=Release
		"-DCMAKE_INSTALL_PREFIX=${CIMBAR_OPENCV_PREFIX}"
	)
	if(CMAKE_GENERATOR_PLATFORM)
		list(APPEND _cv_args -A "${CMAKE_GENERATOR_PLATFORM}")
	endif()
	if(CMAKE_GENERATOR_TOOLSET)
		list(APPEND _cv_args -T "${CMAKE_GENERATOR_TOOLSET}")
	endif()
	if(CMAKE_MAKE_PROGRAM)
		list(APPEND _cv_args "-DCMAKE_MAKE_PROGRAM=${CMAKE_MAKE_PROGRAM}")
	endif()
	foreach(_var CMAKE_C_COMPILER CMAKE_CXX_COMPILER CMAKE_OSX_ARCHITECTURES CMAKE_OSX_DEPLOYMENT_TARGET CMAKE_OSX_SYSROOT)
		if(${_var})
			list(APPEND _cv_args "-D${_var}=${${_var}}")
		endif()
	endforeach()

	list(APPEND _cv_args
		-DBUILD_SHARED_LIBS=OFF
		-DBUILD_WITH_STATIC_CRT=ON
		-DENABLE_PIC=ON
		-DBUILD_LIST=core,imgproc,calib3d
		-DBUILD_ZLIB=ON
		-DBUILD_TESTS=OFF
		-DBUILD_PERF_TESTS=OFF
		-DBUILD_EXAMPLES=OFF
		-DBUILD_DOCS=OFF
		-DBUILD_opencv_apps=OFF
		-DBUILD_JAVA=OFF
		-DBUILD_OBJC=OFF
		-DBUILD_opencv_python2=OFF
		-DBUILD_opencv_python3=OFF
		-DOPENCV_GENERATE_PKGCONFIG=OFF
		-DWITH_IPP=OFF
		-DWITH_ITT=OFF
		-DWITH_OPENCL=OFF
		-DWITH_CUDA=OFF
		-DWITH_EIGEN=OFF
		-DWITH_LAPACK=OFF
		-DWITH_TBB=OFF
		-DWITH_OPENMP=OFF
		-DWITH_PROTOBUF=OFF
		-DWITH_FLATBUFFERS=OFF
		-DWITH_KLEIDICV=OFF
		-DWITH_VA=OFF
		-DWITH_VA_INTEL=OFF
		-DWITH_ADE=OFF
		-DWITH_QUIRC=OFF
		-DWITH_JPEG=OFF
		-DWITH_PNG=OFF
		-DWITH_TIFF=OFF
		-DWITH_WEBP=OFF
		-DWITH_OPENJPEG=OFF
		-DWITH_JASPER=OFF
		-DWITH_OPENEXR=OFF
		-DWITH_FFMPEG=OFF
		-DWITH_GSTREAMER=OFF
		-DWITH_GTK=OFF
		-DWITH_WIN32UI=OFF
	)

	message(STATUS "Building minimal static OpenCV ${CIMBAR_OPENCV_VERSION} into ${CIMBAR_OPENCV_PREFIX} (this takes a while)")
	execute_process(
		COMMAND "${CMAKE_COMMAND}" -S "${_cv_src}" -B "${_cv_build}" ${_cv_args}
		RESULT_VARIABLE _cv_res
	)
	if(NOT _cv_res EQUAL 0)
		message(FATAL_ERROR "OpenCV configure failed (${_cv_res})")
	endif()
	execute_process(
		COMMAND "${CMAKE_COMMAND}" --build "${_cv_build}" --config Release --parallel
		RESULT_VARIABLE _cv_res
	)
	if(NOT _cv_res EQUAL 0)
		message(FATAL_ERROR "OpenCV build failed (${_cv_res})")
	endif()
	execute_process(
		COMMAND "${CMAKE_COMMAND}" --install "${_cv_build}" --config Release
		RESULT_VARIABLE _cv_res
	)
	if(NOT _cv_res EQUAL 0)
		message(FATAL_ERROR "OpenCV install failed (${_cv_res})")
	endif()

	find_package(OpenCV ${CIMBAR_OPENCV_VERSION} EXACT REQUIRED CONFIG
		PATHS "${CIMBAR_OPENCV_PREFIX}" NO_DEFAULT_PATH)
endif()

message(STATUS "Using OpenCV ${OpenCV_VERSION} from ${OpenCV_DIR}")
