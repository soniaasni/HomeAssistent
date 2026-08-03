cmake_minimum_required(VERSION 3.16)
project(motion_control CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(motion_control
    src/axis_controller.cpp
    src/logic.cpp
)
target_include_directories(motion_control PUBLIC include)
target_compile_options(motion_control PRIVATE -Wall -Wextra -Wpedantic)

enable_testing()
add_executable(motion_tests tests/motion_tests.cpp)
target_link_libraries(motion_tests PRIVATE motion_control)
target_compile_options(motion_tests PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME motion_tests COMMAND motion_tests)
