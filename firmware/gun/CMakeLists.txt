function(add_gt_gun target player product)
    add_executable(${target}
        main.c
        usb_descriptors.c
    )
    target_include_directories(${target} PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}
        ${CMAKE_CURRENT_LIST_DIR}/../common
    )
    target_compile_definitions(${target} PRIVATE
        GT_FIRMWARE_VERSION="${GT_FIRMWARE_VERSION}"
        GT_GUN_PLAYER=${player}
        GT_GUN_PRODUCT="${product}"
    )
    target_compile_options(${target} PRIVATE -Wall -Wextra -Werror)
    target_link_libraries(${target} PRIVATE
        gt_common
        pico_stdlib
        pico_bootrom
        hardware_adc
        hardware_watchdog
        tinyusb_device
        tinyusb_board
    )
    pico_enable_stdio_usb(${target} 0)
    pico_enable_stdio_uart(${target} 0)
    pico_add_extra_outputs(${target})
endfunction()

add_gt_gun(gt_gun_p1 1 "GT GUN PLAYER 1")
add_gt_gun(gt_gun_p2 2 "GT GUN PLAYER 2")
