#ifndef GT_DEBOUNCE_H
#define GT_DEBOUNCE_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t pin;
    bool active_low;
    bool raw_active;
    bool stable_active;
    uint16_t debounce_ms;
    uint32_t raw_changed_ms;
} gt_debounced_input_t;

void gt_input_init(gt_debounced_input_t *input,
                   uint8_t pin,
                   bool active_low,
                   uint16_t debounce_ms,
                   uint32_t now_ms);

bool gt_input_update(gt_debounced_input_t *input, uint32_t now_ms);
bool gt_input_is_active(const gt_debounced_input_t *input);

#endif
