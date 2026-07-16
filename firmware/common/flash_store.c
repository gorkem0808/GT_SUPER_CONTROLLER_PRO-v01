#include "flash_store.h"

#include <string.h>

#include "crc32.h"
#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

#define GT_FLASH_HEADER_SIZE 16u
#define GT_FLASH_SLOT_COUNT 2u

// Two different sectors are used as alternating records. Erasing/programming the
// inactive sector never destroys the most recent valid record. On boot, the
// CRC-valid record with the newest sequence number wins.
typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint16_t schema;
    uint16_t payload_size;
    uint32_t sequence;
    uint32_t crc32;
} gt_flash_header_t;

_Static_assert(sizeof(gt_flash_header_t) == GT_FLASH_HEADER_SIZE,
               "Unexpected flash header size");

typedef struct {
    bool valid;
    uint32_t offset;
    uint32_t sequence;
} gt_flash_slot_t;

static uint32_t storage_offset(unsigned slot) {
    return (uint32_t)PICO_FLASH_SIZE_BYTES -
           ((uint32_t)slot + 1u) * FLASH_SECTOR_SIZE;
}

static bool sequence_is_newer(uint32_t candidate, uint32_t reference) {
    const uint32_t distance = candidate - reference;
    return distance != 0u && distance < 0x80000000u;
}

static gt_flash_slot_t inspect_slot(unsigned slot,
                                    uint32_t magic,
                                    uint16_t schema,
                                    size_t payload_size) {
    gt_flash_slot_t result = {
        .valid = false,
        .offset = storage_offset(slot),
        .sequence = 0,
    };

    const uint8_t *record = (const uint8_t *)(XIP_BASE + result.offset);
    gt_flash_header_t header;
    memcpy(&header, record, sizeof(header));

    if (header.magic != magic || header.schema != schema ||
        header.payload_size != payload_size) {
        return result;
    }

    const uint8_t *stored_payload = record + sizeof(header);
    if (gt_crc32(stored_payload, payload_size) != header.crc32) {
        return result;
    }

    result.valid = true;
    result.sequence = header.sequence;
    return result;
}

static gt_flash_slot_t inspect_slot_any_schema(unsigned slot,
                                               uint32_t magic,
                                               size_t payload_size) {
    gt_flash_slot_t result = {
        .valid = false,
        .offset = storage_offset(slot),
        .sequence = 0,
    };

    const uint8_t *record = (const uint8_t *)(XIP_BASE + result.offset);
    gt_flash_header_t header;
    memcpy(&header, record, sizeof(header));

    if (header.magic != magic || header.payload_size != payload_size) {
        return result;
    }

    const uint8_t *stored_payload = record + sizeof(header);
    if (gt_crc32(stored_payload, payload_size) != header.crc32) {
        return result;
    }

    result.valid = true;
    result.sequence = header.sequence;
    return result;
}

static int newest_slot(const gt_flash_slot_t slots[GT_FLASH_SLOT_COUNT]) {
    int newest = -1;
    for (unsigned slot = 0; slot < GT_FLASH_SLOT_COUNT; ++slot) {
        if (!slots[slot].valid) {
            continue;
        }
        if (newest < 0 ||
            sequence_is_newer(slots[slot].sequence, slots[(unsigned)newest].sequence)) {
            newest = (int)slot;
        }
    }
    return newest;
}

bool gt_flash_load(uint32_t magic,
                   uint16_t schema,
                   void *payload,
                   size_t payload_size,
                   uint32_t *sequence_out) {
    if (payload == NULL || payload_size == 0 ||
        payload_size > (FLASH_PAGE_SIZE - sizeof(gt_flash_header_t))) {
        return false;
    }

    gt_flash_slot_t slots[GT_FLASH_SLOT_COUNT];
    for (unsigned slot = 0; slot < GT_FLASH_SLOT_COUNT; ++slot) {
        slots[slot] = inspect_slot(slot, magic, schema, payload_size);
    }

    const int selected = newest_slot(slots);
    if (selected < 0) {
        return false;
    }

    const uint8_t *record =
        (const uint8_t *)(XIP_BASE + slots[(unsigned)selected].offset);
    memcpy(payload, record + sizeof(gt_flash_header_t), payload_size);
    if (sequence_out != NULL) {
        *sequence_out = slots[(unsigned)selected].sequence;
    }
    return true;
}

bool gt_flash_save(uint32_t magic,
                   uint16_t schema,
                   const void *payload,
                   size_t payload_size,
                   uint32_t sequence) {
    if (payload == NULL || payload_size == 0 ||
        payload_size > (FLASH_PAGE_SIZE - sizeof(gt_flash_header_t))) {
        return false;
    }

    // Choose the inactive side by looking at the newest CRC-valid record for
    // this payload even when its schema is older. This keeps a legacy record
    // intact while the first schema-2 record is programmed, so a power loss
    // during firmware migration cannot erase the only usable configuration.
    gt_flash_slot_t slots[GT_FLASH_SLOT_COUNT];
    for (unsigned slot = 0; slot < GT_FLASH_SLOT_COUNT; ++slot) {
        slots[slot] = inspect_slot_any_schema(slot, magic, payload_size);
    }

    const int current = newest_slot(slots);
    const unsigned target = current == 0 ? 1u : 0u;

    uint8_t page[FLASH_PAGE_SIZE];
    memset(page, 0xFF, sizeof(page));

    gt_flash_header_t header = {
        .magic = magic,
        .schema = schema,
        .payload_size = (uint16_t)payload_size,
        .sequence = sequence,
        .crc32 = gt_crc32(payload, payload_size),
    };
    memcpy(page, &header, sizeof(header));
    memcpy(page + sizeof(header), payload, payload_size);

    const uint32_t target_offset = storage_offset(target);
    const uint32_t irq_state = save_and_disable_interrupts();
    flash_range_erase(target_offset, FLASH_SECTOR_SIZE);
    flash_range_program(target_offset, page, FLASH_PAGE_SIZE);
    restore_interrupts(irq_state);

    const gt_flash_slot_t written =
        inspect_slot(target, magic, schema, payload_size);
    if (!written.valid || written.sequence != sequence) {
        return false;
    }

    const uint8_t *stored_payload =
        (const uint8_t *)(XIP_BASE + written.offset + sizeof(gt_flash_header_t));
    return memcmp(stored_payload, payload, payload_size) == 0;
}
