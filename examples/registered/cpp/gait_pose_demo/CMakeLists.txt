cmake_minimum_required(VERSION 3.10)
project(registered_gait_pose_demo)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

add_executable(registered_gait_pose_demo main.cpp)
target_link_libraries(registered_gait_pose_demo CURL::libcurl)
