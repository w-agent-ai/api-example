cmake_minimum_required(VERSION 3.10)
project(persondet_cpp)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG")

option(PERSONDET_ENABLE_NATIVE "Enable -march=native for local maximum CPU speed" ON)
if(PERSONDET_ENABLE_NATIVE AND NOT MSVC)
    add_compile_options($<$<CONFIG:Release>:-march=native>)
endif()

add_library(persondet STATIC
    persondet.cpp
    persondet_weights.cpp
)
target_include_directories(persondet PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

find_package(OpenMP QUIET)
if(OpenMP_CXX_FOUND)
    target_link_libraries(persondet PUBLIC OpenMP::OpenMP_CXX)
endif()

find_package(OpenCV QUIET)
if(OpenCV_FOUND)
    add_executable(image_detect_demo image_detect_demo.cpp)
    target_link_libraries(image_detect_demo persondet ${OpenCV_LIBS})

    add_executable(video_sequence_demo video_sequence_demo.cpp)
    target_link_libraries(video_sequence_demo persondet ${OpenCV_LIBS})

    add_executable(onnx_demo onnx_demo.cpp)
    target_link_libraries(onnx_demo ${OpenCV_LIBS})
endif()
