cmake_minimum_required(VERSION 3.16)
project(stashy_engine CXX)

set(CMAKE_CXX_STANDARD 17)

find_package(CURL REQUIRED)
find_package(PostgreSQL REQUIRED)

add_executable(stashy_engine
  src/main.cpp
  src/engine.cpp
  src/db.cpp
  src/fetcher.cpp
)

target_include_directories(stashy_engine PRIVATE
  ${CURL_INCLUDE_DIRS}
  ${PostgreSQL_INCLUDE_DIRS}
)

target_link_libraries(stashy_engine PRIVATE
  CURL::libcurl
  ${PostgreSQL_LIBRARIES}
)

# Optional: static linking for portability
# set_target_properties(stashy_engine PROPERTIES LINK_SEARCH_START_STATIC ON)
