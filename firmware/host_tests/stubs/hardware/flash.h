#ifndef GT_HOST_TEST_HARDWARE_FLASH_H
#define GT_HOST_TEST_HARDWARE_FLASH_H

#include <stddef.h>
#include <stdint.h>

#define PICO_FLASH_SIZE_BYTES 8192u
#define FLASH_SECTOR_SIZE 4096u
#define FLASH_PAGE_SIZE 256u

extern uint8_t gt_host_test_flash[PICO_FLASH_SIZE_BYTES];
#define XIP_BASE ((uintptr_t)gt_host_test_flash)

void flash_range_erase(uint32_t flash_offs, size_t count);
void flash_range_program(uint32_t flash_offs, const uint8_t *data, size_t count);

#endif
