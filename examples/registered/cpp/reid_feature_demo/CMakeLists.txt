cmake_minimum_required(VERSION 3.10)
project(w_agent_reid_feature_demo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenCV REQUIRED)
find_package(CURL REQUIRED)

add_executable(w_agent_reid_feature_demo main.cpp)
target_link_libraries(w_agent_reid_feature_demo PRIVATE ${OpenCV_LIBS} CURL::libcurl)
