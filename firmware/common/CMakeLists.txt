add_library(gt_common STATIC
    crc32.c
    debounce.c
    flash_store.c
)

target_include_directories(gt_common PUBLIC ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(gt_common PUBLIC
    pico_stdlib
    hardware_flash
    hardware_sync
)
target_compile_options(gt_common PRIVATE -Wall -Wextra -Werror)
