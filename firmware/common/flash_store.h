#ifndef GT_FLASH_STORE_H
#define GT_FLASH_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool gt_flash_load(uint32_t magic,
                   uint16_t schema,
                   void *payload,
                   size_t payload_size,
                   uint32_t *sequence_out);

bool gt_flash_save(uint32_t magic,
                   uint16_t schema,
                   const void *payload,
                   size_t payload_size,
                   uint32_t sequence);

#endif
