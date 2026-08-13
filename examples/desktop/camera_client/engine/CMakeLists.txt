cmake_minimum_required(VERSION 3.16)
project(w_agent_local_engine)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenCV REQUIRED)

add_executable(w-agent-local-engine
    main.cpp
)

target_link_libraries(w-agent-local-engine PRIVATE ${OpenCV_LIBS})
