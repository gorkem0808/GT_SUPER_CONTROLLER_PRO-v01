add_executable(gt_controller
    main.c
    usb_descriptors.c
)

target_include_directories(gt_controller PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/../common
)
target_compile_definitions(gt_controller PRIVATE
    GT_FIRMWARE_VERSION="${GT_FIRMWARE_VERSION}"
)
target_compile_options(gt_controller PRIVATE -Wall -Wextra -Werror)
target_link_libraries(gt_controller PRIVATE
    gt_common
    pico_stdlib
    pico_bootrom
    hardware_watchdog
    tinyusb_device
    tinyusb_board
)
pico_enable_stdio_usb(gt_controller 0)
pico_enable_stdio_uart(gt_controller 0)
pico_add_extra_outputs(gt_controller)
