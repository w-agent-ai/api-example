cmake_minimum_required(VERSION 3.10)
project(registered_video_demo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

add_executable(registered_video_demo main.cpp)
target_link_libraries(registered_video_demo PRIVATE CURL::libcurl)
