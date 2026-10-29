cmake_minimum_required(VERSION 3.21)

# Builds the libcimbar C API (src/lib/cimbar_js) as a self-contained shared library for the
# python bindings: no GUI/OpenGL, OpenCV linked in statically, only the cimbare_*/cimbard_* functions exported.
project(pycimbar LANGUAGES C CXX)

set(LIBCIMBAR_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# static MSVC runtime: python only ships vcruntime140, not msvcp140/concrt140.
# (the policy default also reaches libcimbar's subdirectories, which ask for an older cmake)
set(CMAKE_POLICY_DEFAULT_CMP0091 NEW)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")

include(cmake/MinimalOpenCV.cmake)

# libcimbar's own build, trimmed to the libraries the C API needs
set(BUILD_GUI OFF CACHE BOOL "" FORCE)
set(BUILD_CLI OFF CACHE BOOL "" FORCE)
set(DISABLE_TESTS true)
set(CIMBAR_PORTABLE true)  # no -march=native: the wheels must run on other machines
set(CPPFILESYSTEM "")
set(OPENCV_LIBS opencv_calib3d opencv_imgproc opencv_core)
add_subdirectory("${LIBCIMBAR_ROOT}" libcimbar EXCLUDE_FROM_ALL)

set(CIMBAR_EXPORTS
	cimbare_init_encode
	cimbare_encode_bufsize
	cimbare_encode
	cimbare_configure
	cimbare_next_frame
	cimbare_get_frame_buff
	cimbare_get_frame_dims
	cimbare_get_aspect_ratio
	cimbard_get_report
	cimbard_get_bufsize
	cimbard_scan_extract_decode
	cimbard_fountain_decode
	cimbard_get_filesize
	cimbard_get_filename
	cimbard_get_decompress_bufsize
	cimbard_decompress_read
	cimbard_configure_decode
	cimbard_reset
)

add_library(cimbar SHARED
	"${LIBCIMBAR_ROOT}/src/lib/cimbar_js/cimbar_js.cpp"
	"${LIBCIMBAR_ROOT}/src/lib/cimbar_js/cimbar_recv_js.cpp"
)
target_compile_features(cimbar PRIVATE cxx_std_17)
target_compile_definitions(cimbar PRIVATE CIMBAR_NO_GL CIMBAR_QUIET)
target_include_directories(cimbar PRIVATE
	"${LIBCIMBAR_ROOT}/src/lib"
	"${LIBCIMBAR_ROOT}/src/third_party_lib"
	${OpenCV_INCLUDE_DIRS}
)
target_link_libraries(cimbar PRIVATE
	cimb_translator
	extractor
	correct_static
	wirehair
	zstd
	${OPENCV_LIBS}
)

# export only the C API, keeping the statically linked OpenCV private
# (so it can't clash with another OpenCV in the same process, e.g. opencv-python)
if(WIN32)
	list(JOIN CIMBAR_EXPORTS "\n\t" _exports)
	file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/cimbar.def" "LIBRARY cimbar\nEXPORTS\n\t${_exports}\n")
	target_sources(cimbar PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/cimbar.def")
	if(MSVC)
		target_compile_options(cimbar PRIVATE /FI iso646.h /utf-8)
	endif()
elseif(APPLE)
	list(TRANSFORM CIMBAR_EXPORTS PREPEND "_")
	list(JOIN CIMBAR_EXPORTS "\n" _exports)
	file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/cimbar.exports" "${_exports}\n")
	target_link_options(cimbar PRIVATE "LINKER:-exported_symbols_list,${CMAKE_CURRENT_BINARY_DIR}/cimbar.exports" "LINKER:-dead_strip")
else()
	list(JOIN CIMBAR_EXPORTS ";\n\t\t" _exports)
	file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/cimbar.map" "{\n\tglobal:\n\t\t${_exports};\n\tlocal: *;\n};\n")
	target_link_options(cimbar PRIVATE
		"LINKER:--version-script=${CMAKE_CURRENT_BINARY_DIR}/cimbar.map"
		"LINKER:--exclude-libs,ALL"
		"LINKER:--gc-sections"
	)
endif()

install(TARGETS cimbar
	RUNTIME DESTINATION pycimbar COMPONENT python
	LIBRARY DESTINATION pycimbar COMPONENT python
	ARCHIVE DESTINATION lib COMPONENT dev
)
