cmake_minimum_required(VERSION 3.10)
project(w_agent_face_feature_demo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenCV REQUIRED)
find_package(CURL REQUIRED)

set(LOCAL_ONNXRUNTIME_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/third_party/onnxruntime-linux-x64")
set(REPO_ONNXRUNTIME_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../local_video_to_sequence_demo/third_party/onnxruntime-linux-x64")
if(EXISTS "${LOCAL_ONNXRUNTIME_ROOT}/include/onnxruntime_cxx_api.h")
  set(ONNXRUNTIME_ROOT "${LOCAL_ONNXRUNTIME_ROOT}" CACHE PATH "ONNX Runtime CPU package root")
else()
  set(ONNXRUNTIME_ROOT "${REPO_ONNXRUNTIME_ROOT}" CACHE PATH "ONNX Runtime CPU package root")
endif()
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

add_library(facedet_onnx STATIC facedet_onnx.cpp)
target_include_directories(facedet_onnx PUBLIC ${CMAKE_CURRENT_SOURCE_DIR} ${ONNXRUNTIME_INCLUDE_DIR})
target_link_libraries(facedet_onnx PUBLIC onnxruntime ${OpenCV_LIBS})

add_executable(w_agent_face_feature_demo main.cpp)
target_link_libraries(w_agent_face_feature_demo PRIVATE facedet_onnx ${OpenCV_LIBS} CURL::libcurl)
set_target_properties(w_agent_face_feature_demo PROPERTIES
  BUILD_RPATH "${ONNXRUNTIME_ROOT}/lib"
  INSTALL_RPATH "$ORIGIN/../third_party/onnxruntime-linux-x64/lib"
)
add_custom_command(TARGET w_agent_face_feature_demo POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${CMAKE_CURRENT_SOURCE_DIR}/face_detect.onnx"
    "$<TARGET_FILE_DIR:w_agent_face_feature_demo>/face_detect.onnx"
)
