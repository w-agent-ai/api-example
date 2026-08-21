cmake_minimum_required(VERSION 3.10)
project(w_agent_object_search_demo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

add_executable(w_agent_object_search_demo main.cpp)
target_link_libraries(w_agent_object_search_demo PRIVATE CURL::libcurl)
