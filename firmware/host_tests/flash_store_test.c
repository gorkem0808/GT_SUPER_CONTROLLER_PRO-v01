#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "flash_store.h"
#include "hardware/flash.h"

#define TEST_MAGIC 0x47545453u
#define SCHEMA_LEGACY 1u
#define SCHEMA_CURRENT 2u

uint8_t gt_host_test_flash[PICO_FLASH_SIZE_BYTES];

void flash_range_erase(uint32_t flash_offs, size_t count) {
    assert((size_t)flash_offs + count <= sizeof(gt_host_test_flash));
    memset(gt_host_test_flash + flash_offs, 0xFF, count);
}

void flash_range_program(uint32_t flash_offs, const uint8_t *data, size_t count) {
    assert(data != NULL);
    assert((size_t)flash_offs + count <= sizeof(gt_host_test_flash));
    memcpy(gt_host_test_flash + flash_offs, data, count);
}

uint32_t save_and_disable_interrupts(void) {
    return 0u;
}

void restore_interrupts(uint32_t status) {
    (void)status;
}

typedef struct {
    uint32_t value;
    uint8_t reserved[28];
} test_payload_t;

static test_payload_t load_payload(uint16_t schema, uint32_t *sequence) {
    test_payload_t payload = {0};
    assert(gt_flash_load(TEST_MAGIC, schema, &payload, sizeof(payload), sequence));
    return payload;
}

int main(void) {
    memset(gt_host_test_flash, 0xFF, sizeof(gt_host_test_flash));

    const test_payload_t legacy = {.value = 101u};
    assert(gt_flash_save(TEST_MAGIC, SCHEMA_LEGACY, &legacy, sizeof(legacy), 7u));

    uint32_t sequence = 0u;
    test_payload_t loaded = load_payload(SCHEMA_LEGACY, &sequence);
    assert(sequence == 7u);
    assert(loaded.value == legacy.value);

    // The first schema-2 write must use the opposite sector. The only valid
    // schema-1 record must remain readable until a schema-2 record is proven.
    const test_payload_t current = {.value = 202u};
    assert(gt_flash_save(TEST_MAGIC, SCHEMA_CURRENT, &current, sizeof(current), 8u));

    loaded = load_payload(SCHEMA_CURRENT, &sequence);
    assert(sequence == 8u);
    assert(loaded.value == current.value);

    loaded = load_payload(SCHEMA_LEGACY, &sequence);
    assert(sequence == 7u);
    assert(loaded.value == legacy.value);

    // Once one current-schema record exists, the next current write may safely
    // reuse the legacy side while preserving the last current record.
    const test_payload_t current_next = {.value = 303u};
    assert(gt_flash_save(
        TEST_MAGIC, SCHEMA_CURRENT, &current_next, sizeof(current_next), 9u));
    loaded = load_payload(SCHEMA_CURRENT, &sequence);
    assert(sequence == 9u);
    assert(loaded.value == current_next.value);

    puts("flash_store schema migration test: passed");
    return 0;
}
