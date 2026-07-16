#include "debounce.h"

#include "pico/stdlib.h"

static bool read_active(const gt_debounced_input_t *input) {
    const bool level = gpio_get(input->pin) != 0;
    return input->active_low ? !level : level;
}

void gt_input_init(gt_debounced_input_t *input,
                   uint8_t pin,
                   bool active_low,
                   uint16_t debounce_ms,
                   uint32_t now_ms) {
    input->pin = pin;
    input->active_low = active_low;
    input->debounce_ms = debounce_ms;
    gpio_init(pin);
    gpio_set_dir(pin, GPIO_IN);
    if (active_low) {
        gpio_pull_up(pin);
    } else {
        gpio_pull_down(pin);
    }
    input->raw_active = read_active(input);
    input->stable_active = input->raw_active;
    input->raw_changed_ms = now_ms;
}

bool gt_input_update(gt_debounced_input_t *input, uint32_t now_ms) {
    const bool current = read_active(input);
    if (current != input->raw_active) {
        input->raw_active = current;
        input->raw_changed_ms = now_ms;
    }
    if (input->stable_active != input->raw_active &&
        (uint32_t)(now_ms - input->raw_changed_ms) >= input->debounce_ms) {
        input->stable_active = input->raw_active;
        return true;
    }
    return false;
}

bool gt_input_is_active(const gt_debounced_input_t *input) {
    return input->stable_active;
}
