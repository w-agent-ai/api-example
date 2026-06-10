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

add_library(persondet STATIC
    persondet.cpp
    persondet_weights.cpp
)
target_include_directories(persondet PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
if(OpenMP_CXX_FOUND)
    target_link_libraries(persondet PUBLIC OpenMP::OpenMP_CXX)
endif()

add_executable(local_video_sequence_extractor video_sequence_demo.cpp)
target_link_libraries(local_video_sequence_extractor persondet ${OpenCV_LIBS})
