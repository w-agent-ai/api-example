cmake_minimum_required(VERSION 3.10)
project(registered_cpp_local_video_to_sequence_demo)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG")

option(PERSONDET_ENABLE_NATIVE "Enable -march=native for local maximum CPU speed" ON)
if(PERSONDET_ENABLE_NATIVE AND NOT MSVC)
    add_compile_options($<$<CONFIG:Release>:-march=native>)
endif()

find_package(OpenMP QUIET)
find_package(OpenCV REQUIRED)
find_package(CURL REQUIRED)

set(ONNXRUNTIME_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/third_party/onnxruntime-linux-x64" CACHE PATH "ONNX Runtime CPU package root")
set(ONNXRUNTIME_INCLUDE_DIR "${ONNXRUNTIME_ROOT}/include")
set(ONNXRUNTIME_LIBRARY "${ONNXRUNTIME_ROOT}/lib/libonnxruntime.so.1.23.2")

if(NOT EXISTS "${ONNXRUNTIME_INCLUDE_DIR}/onnxruntime_cxx_api.h")
    message(FATAL_ERROR "ONNX Runtime header not found: ${ONNXRUNTIME_INCLUDE_DIR}/onnxruntime_cxx_api.h")
endif()
if(NOT EXISTS "${ONNXRUNTIME_LIBRARY}")
    message(FATAL_ERROR "ONNX Runtime library not found: ${ONNXRUNTIME_LIBRARY}")
endif()

add_library(onnxruntime SHARED IMPORTED)
set_target_properties(onnxruntime PROPERTIES
    IMPORTED_LOCATION "${ONNXRUNTIME_LIBRARY}"
)

add_library(persondet STATIC
    persondet.cpp
)
target_include_directories(persondet PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${ONNXRUNTIME_INCLUDE_DIR}
)
target_link_libraries(persondet PUBLIC onnxruntime)
if(OpenMP_CXX_FOUND)
    target_link_libraries(persondet PUBLIC OpenMP::OpenMP_CXX)
endif()

add_executable(local_video_sequence_extractor video_sequence_demo.cpp)
target_link_libraries(local_video_sequence_extractor persondet ${OpenCV_LIBS})
set_target_properties(local_video_sequence_extractor PROPERTIES
    BUILD_RPATH "${ONNXRUNTIME_ROOT}/lib"
    INSTALL_RPATH "$ORIGIN/../third_party/onnxruntime-linux-x64/lib"
)
add_custom_command(TARGET local_video_sequence_extractor POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/gait_detect.onnx"
        "$<TARGET_FILE_DIR:local_video_sequence_extractor>/gait_detect.onnx"
)

add_executable(local_video_to_gait_api_demo local_video_api_demo.cpp)
target_link_libraries(local_video_to_gait_api_demo CURL::libcurl)
