cmake_minimum_required(VERSION 3.10)
project(registered_sequence_demo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

add_executable(registered_sequence_demo main.cpp)
target_link_libraries(registered_sequence_demo PRIVATE CURL::libcurl)
