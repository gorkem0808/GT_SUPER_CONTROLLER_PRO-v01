#include <ctype.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "class/hid/hid.h"
#include "debounce.h"
#include "flash_store.h"
#include "hardware/watchdog.h"
#include "pico/bootrom.h"
#include "pico/stdlib.h"
#include "tusb.h"

#ifndef GT_FIRMWARE_VERSION
#define GT_FIRMWARE_VERSION "dev"
#endif

#define CONTROLLER_FLASH_MAGIC 0x47544343u
#define CONTROLLER_FLASH_SCHEMA 2u
#define CONTROLLER_FLASH_SCHEMA_LEGACY 1u
#define INPUT_COUNT 7u
#define PLAYER_COUNT 2u
#define RELAY_P1_PIN 27u
#define RELAY_P2_PIN 26u
#define CDC_LINE_MAX 192u
#define MAINTENANCE_TIMEOUT_MS 180000u
#define CALIBRATION_REQUEST_HOLD_MS 10000u
#define MOTION_DISABLE_TIMEOUT_MS 180000u

typedef enum {
    INPUT_COIN = 0,
    INPUT_P1_START,
    INPUT_P1_TRIGGER,
    INPUT_P1_BOMB,
    INPUT_P2_START,
    INPUT_P2_TRIGGER,
    INPUT_P2_BOMB,
} input_id_t;

typedef enum {
    RELAY_MODE_OFF = 0,
    RELAY_MODE_PULSE = 1,
    RELAY_MODE_FOLLOW = 2,
} relay_mode_t;

typedef struct {
    uint8_t relay_active_low;
    uint8_t relay_mode;
    uint8_t trigger_hid_enabled;
    uint8_t reserved0;
    uint16_t pulse_ms;
    uint16_t cooldown_ms;
    uint16_t follow_max_ms;
    uint16_t key_pulse_ms;
    uint32_t inactivity_ms;
    uint8_t keycodes[INPUT_COUNT];
    uint8_t reserved2[9];
} controller_config_t;

_Static_assert(sizeof(controller_config_t) <= 96, "Controller config too large");

typedef struct {
    bool output_on;
    bool armed;
    bool follow_forced_off;
    uint32_t last_activity_ms;
    uint32_t off_at_ms;
    uint32_t cooldown_until_ms;
    uint32_t follow_started_ms;
} relay_state_t;

static const uint8_t input_pins[INPUT_COUNT] = {2, 3, 4, 5, 6, 7, 8};
static const char *const input_names[INPUT_COUNT] = {
    "COIN", "P1_START", "P1_TRIGGER", "P1_BOMB",
    "P2_START", "P2_TRIGGER", "P2_BOMB",
};
static const int8_t input_players[INPUT_COUNT] = {-1, 0, 0, 0, 1, 1, 1};

static gt_debounced_input_t inputs[INPUT_COUNT];
static controller_config_t config;
static uint32_t config_sequence;
static relay_state_t relays[PLAYER_COUNT];
static bool keyboard_dirty = true;
static bool key_pulse_active[INPUT_COUNT];
static uint32_t key_pulse_until_ms[INPUT_COUNT];
static bool trigger_hid_suppressed_until_release[PLAYER_COUNT];
static bool usb_mounted;
static bool watchdog_rebooted;
static char cdc_line[CDC_LINE_MAX];
static size_t cdc_line_length;
static bool cdc_discard_until_newline;
static uint32_t last_status_ms;
static bool last_cdc_connected;
static bool maintenance_mode;
static uint32_t maintenance_deadline_ms;
static bool gun_motion_enabled = true;
static uint32_t motion_change_id;
static uint32_t motion_disable_deadline_ms;
static bool start_pending[PLAYER_COUNT];
static bool start_chord_active;
static bool start_chord_cancelled;
static bool start_chord_fired;
static uint32_t start_chord_started_ms;

static void suppress_held_trigger_keys(void);
static void set_maintenance_mode(bool enabled, uint32_t now);

static uint32_t now_ms(void) {
    return (uint32_t)(time_us_64() / 1000u);
}

static bool time_reached(uint32_t now, uint32_t deadline) {
    return (int32_t)(now - deadline) >= 0;
}

static const char *json_bool(bool value) {
    return value ? "true" : "false";
}

static void cdc_printf(const char *format, ...) {
    if (!tud_cdc_connected()) {
        return;
    }

    char buffer[512];
    va_list args;
    va_start(args, format);
    const int written = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);

    if (written <= 0 || (size_t)written >= sizeof(buffer)) {
        // vsnprintf reports the required length when truncation occurs. Never
        // transmit that truncated fragment because it may not contain a newline.
        return;
    }
    const size_t length = (size_t)written;
    // Never place a partial JSON line in TinyUSB's TX ring. A truncated line
    // would corrupt the desktop protocol until the next newline. Status messages
    // are disposable, so drop the whole line when the host is not keeping up.
    const uint32_t write_available = tud_cdc_write_available();
    if ((size_t)write_available < length) {
        return;
    }
    if ((size_t)tud_cdc_write(buffer, (uint32_t)length) == length) {
        tud_cdc_write_flush();
    }
}

static void config_defaults(controller_config_t *out) {
    memset(out, 0, sizeof(*out));
    out->relay_active_low = 1;
    out->relay_mode = RELAY_MODE_PULSE;
    // Both gun triggers are wired to the Controller Pico. Their HID output is
    // therefore enabled by default so a fresh installation can fire immediately.
    out->trigger_hid_enabled = 1;
    out->pulse_ms = 60;
    out->cooldown_ms = 120;
    out->follow_max_ms = 250;
    out->key_pulse_ms = 80;
    out->inactivity_ms = 300000;
    out->keycodes[INPUT_COIN] = HID_KEY_1;
    out->keycodes[INPUT_P1_START] = HID_KEY_2;
    out->keycodes[INPUT_P1_TRIGGER] = HID_KEY_3;
    out->keycodes[INPUT_P1_BOMB] = HID_KEY_4;
    out->keycodes[INPUT_P2_START] = HID_KEY_5;
    out->keycodes[INPUT_P2_TRIGGER] = HID_KEY_6;
    out->keycodes[INPUT_P2_BOMB] = HID_KEY_7;
}

static bool config_valid(const controller_config_t *candidate) {
    return candidate->relay_active_low <= 1 &&
           candidate->relay_mode <= RELAY_MODE_FOLLOW &&
           candidate->trigger_hid_enabled <= 1 &&
           candidate->pulse_ms >= 10 && candidate->pulse_ms <= 500 &&
           candidate->cooldown_ms >= 20 && candidate->cooldown_ms <= 2000 &&
           candidate->follow_max_ms >= 20 && candidate->follow_max_ms <= 1000 &&
           candidate->key_pulse_ms >= 20 && candidate->key_pulse_ms <= 200 &&
           candidate->inactivity_ms <= 3600000u;
}

static void load_config(void) {
    controller_config_t loaded;
    uint32_t sequence = 0;
    if (gt_flash_load(CONTROLLER_FLASH_MAGIC,
                      CONTROLLER_FLASH_SCHEMA,
                      &loaded,
                      sizeof(loaded),
                      &sequence) &&
        config_valid(&loaded)) {
        config = loaded;
        config_sequence = sequence;
        return;
    }

    // Schema 1 used trigger buttons on the Gun Picos and could therefore have
    // Controller trigger HID disabled. Preserve relay/key settings during the
    // upgrade, but force Controller trigger output on for the new wiring model.
    if (gt_flash_load(CONTROLLER_FLASH_MAGIC,
                      CONTROLLER_FLASH_SCHEMA_LEGACY,
                      &loaded,
                      sizeof(loaded),
                      &sequence) &&
        config_valid(&loaded)) {
        config = loaded;
        config.trigger_hid_enabled = 1;
        config_sequence = sequence;
        return;
    }

    config_defaults(&config);
    config_sequence = 0;
}

static uint8_t relay_pin(unsigned player) {
    return player == 0 ? RELAY_P1_PIN : RELAY_P2_PIN;
}

static bool relay_off_level(void) {
    return config.relay_active_low != 0;
}

static void relay_write(unsigned player, bool on) {
    if (player >= PLAYER_COUNT) {
        return;
    }
    const bool level = config.relay_active_low ? !on : on;
    gpio_put(relay_pin(player), level);
    relays[player].output_on = on;
}

static void relay_configure_off_pull(unsigned player) {
    const uint8_t pin = relay_pin(player);
    if (config.relay_active_low) {
        gpio_pull_up(pin);
    } else {
        gpio_pull_down(pin);
    }
}

static void relay_gpio_init(unsigned player) {
    const uint8_t pin = relay_pin(player);
    gpio_init(pin);
    relay_configure_off_pull(player);
    gpio_put(pin, relay_off_level());
    gpio_set_dir(pin, GPIO_OUT);
    gpio_put(pin, relay_off_level());
    relays[player].output_on = false;
}

static void relay_all_off(void) {
    for (unsigned player = 0; player < PLAYER_COUNT; ++player) {
        relay_write(player, false);
    }
}

static void relay_trigger_rising(unsigned player, uint32_t now) {
    if (maintenance_mode || player >= PLAYER_COUNT || !relays[player].armed ||
        config.relay_mode == RELAY_MODE_OFF ||
        !time_reached(now, relays[player].cooldown_until_ms)) {
        return;
    }

    relays[player].follow_forced_off = false;
    relay_write(player, true);
    relays[player].cooldown_until_ms = now + config.cooldown_ms;

    if (config.relay_mode == RELAY_MODE_PULSE) {
        relays[player].off_at_ms = now + config.pulse_ms;
    } else {
        relays[player].follow_started_ms = now;
    }
}

static void relay_trigger_released(unsigned player, uint32_t now) {
    if (player >= PLAYER_COUNT) {
        return;
    }
    if (config.relay_mode == RELAY_MODE_FOLLOW) {
        relay_write(player, false);
        relays[player].cooldown_until_ms = now + config.cooldown_ms;
    }
    relays[player].follow_forced_off = false;
}

static void relay_update(uint32_t now) {
    for (unsigned player = 0; player < PLAYER_COUNT; ++player) {
        relay_state_t *state = &relays[player];

        if (config.inactivity_ms > 0 && state->armed &&
            (uint32_t)(now - state->last_activity_ms) >= config.inactivity_ms) {
            state->armed = false;
            state->follow_forced_off = true;
            relay_write(player, false);
            cdc_printf("{\"event\":\"inactivity\",\"player\":%u,\"relay\":false}\r\n",
                       player + 1u);
        }

        if (!state->output_on) {
            continue;
        }

        if (config.relay_mode == RELAY_MODE_PULSE &&
            time_reached(now, state->off_at_ms)) {
            relay_write(player, false);
        } else if (config.relay_mode == RELAY_MODE_FOLLOW &&
                   (uint32_t)(now - state->follow_started_ms) >= config.follow_max_ms) {
            relay_write(player, false);
            state->follow_forced_off = true;
            cdc_printf("{\"event\":\"relay_safety_cutoff\",\"player\":%u}\r\n",
                       player + 1u);
        }
    }
}

static bool input_uses_key_pulse(size_t index) {
    return index != INPUT_P1_TRIGGER && index != INPUT_P2_TRIGGER;
}

static bool input_is_start(size_t index) {
    return index == INPUT_P1_START || index == INPUT_P2_START;
}

static unsigned start_player_from_input(size_t index) {
    return index == INPUT_P1_START ? 0u : 1u;
}

static void start_key_pulse(unsigned player, uint32_t now) {
    if (player >= PLAYER_COUNT || maintenance_mode) {
        return;
    }
    const size_t index = player == 0u ? INPUT_P1_START : INPUT_P2_START;
    key_pulse_active[index] = true;
    key_pulse_until_ms[index] = now + config.key_pulse_ms;
    keyboard_dirty = true;
}

static void clear_start_command_state(void) {
    bool changed = false;
    for (unsigned player = 0; player < PLAYER_COUNT; ++player) {
        changed = changed || start_pending[player];
        start_pending[player] = false;
    }
    changed = changed || key_pulse_active[INPUT_P1_START] ||
              key_pulse_active[INPUT_P2_START];
    key_pulse_active[INPUT_P1_START] = false;
    key_pulse_active[INPUT_P2_START] = false;
    if (changed) {
        keyboard_dirty = true;
    }
}

static void set_gun_motion_enabled(bool enabled, const char *source) {
    if (gun_motion_enabled != enabled) {
        gun_motion_enabled = enabled;
        ++motion_change_id;
    }
    motion_disable_deadline_ms =
        enabled ? 0u : now_ms() + MOTION_DISABLE_TIMEOUT_MS;
    cdc_printf("{\"event\":\"motion_state\",\"role\":\"controller\","
               "\"enabled\":%s,\"source\":\"%s\","
               "\"change_id\":%lu}\r\n",
               json_bool(enabled),
               source != NULL ? source : "unknown",
               (unsigned long)motion_change_id);
}

static void motion_timeout_task(uint32_t now) {
    if (gun_motion_enabled || motion_disable_deadline_ms == 0u ||
        !time_reached(now, motion_disable_deadline_ms)) {
        return;
    }
    set_gun_motion_enabled(true, "motion_timeout");
}

static void start_chord_task(uint32_t now) {
    const bool p1_start = gt_input_is_active(&inputs[INPUT_P1_START]);
    const bool p2_start = gt_input_is_active(&inputs[INPUT_P2_START]);
    const bool both_pressed = p1_start && p2_start;

    if (maintenance_mode) {
        if (p1_start || p2_start) {
            start_chord_active = true;
            start_chord_cancelled = true;
            start_chord_fired = false;
            clear_start_command_state();
        } else {
            start_chord_active = false;
            start_chord_cancelled = false;
            start_chord_fired = false;
        }
        return;
    }

    if (!start_chord_active && both_pressed) {
        start_chord_active = true;
        start_chord_cancelled = false;
        start_chord_fired = false;
        start_chord_started_ms = now;
        clear_start_command_state();
        cdc_printf("{\"event\":\"calibration_hold_started\",\"role\":\"controller\","
                   "\"hold_ms\":%lu}\r\n",
                   (unsigned long)CALIBRATION_REQUEST_HOLD_MS);
        return;
    }

    if (!start_chord_active) {
        return;
    }

    // Once the two buttons overlap, neither Start command is forwarded until
    // both buttons are released. This prevents a failed long-press attempt from
    // spending credits or starting players accidentally.
    clear_start_command_state();

    if (!both_pressed && !start_chord_fired) {
        start_chord_cancelled = true;
    }

    if (both_pressed && !start_chord_cancelled && !start_chord_fired &&
        (uint32_t)(now - start_chord_started_ms) >=
            CALIBRATION_REQUEST_HOLD_MS) {
        start_chord_fired = true;
        set_gun_motion_enabled(false, "calibration_start_buttons");
        cdc_printf("{\"event\":\"calibration_request\","
                   "\"role\":\"controller\","
                   "\"source\":\"start_buttons\","
                   "\"hold_ms\":%lu,\"change_id\":%lu}\r\n",
                   (unsigned long)CALIBRATION_REQUEST_HOLD_MS,
                   (unsigned long)motion_change_id);
        // Enter maintenance immediately so no game input or recoil can leak
        // through while the Windows calibration UI is being restored.
        set_maintenance_mode(true, now);
        return;
    }

    if (!p1_start && !p2_start) {
        if (start_chord_cancelled) {
            cdc_printf("{\"event\":\"calibration_hold_cancelled\","
                       "\"role\":\"controller\"}\r\n");
        }
        start_chord_active = false;
        start_chord_cancelled = false;
        start_chord_fired = false;
    }
}

static void keyboard_task(uint32_t now) {
    for (size_t i = 0; i < INPUT_COUNT; ++i) {
        if (key_pulse_active[i] && time_reached(now, key_pulse_until_ms[i])) {
            key_pulse_active[i] = false;
            keyboard_dirty = true;
        }
    }

    if (!keyboard_dirty || !usb_mounted || !tud_hid_ready()) {
        return;
    }

    uint8_t keycodes[6] = {0};
    size_t output_index = 0;
    for (size_t i = 0; i < INPUT_COUNT && output_index < 6; ++i) {
        bool active = !maintenance_mode &&
                      (input_uses_key_pulse(i)
                           ? key_pulse_active[i]
                           : gt_input_is_active(&inputs[i]));
        if (i == INPUT_P1_TRIGGER || i == INPUT_P2_TRIGGER) {
            const unsigned player = i == INPUT_P1_TRIGGER ? 0u : 1u;
            if (!config.trigger_hid_enabled ||
                trigger_hid_suppressed_until_release[player]) {
                active = false;
            }
        }
        if (!active) {
            continue;
        }
        if (config.keycodes[i] != HID_KEY_NONE) {
            keycodes[output_index++] = config.keycodes[i];
        }
    }

    if (tud_hid_keyboard_report(0, 0, keycodes)) {
        keyboard_dirty = false;
    }
}

static void send_info(void) {
    cdc_printf("{\"type\":\"info\",\"role\":\"controller\","
               "\"name\":\"GT SUPER CONTROLLER\",\"version\":\"%s\","
               "\"protocol\":3,\"watchdog_reboot\":%s}\r\n",
               GT_FIRMWARE_VERSION,
               json_bool(watchdog_rebooted));
}

static const char *relay_mode_name(void) {
    switch ((relay_mode_t)config.relay_mode) {
        case RELAY_MODE_PULSE:
            return "PULSE";
        case RELAY_MODE_FOLLOW:
            return "FOLLOW";
        default:
            return "OFF";
    }
}

static void send_config(void) {
    cdc_printf("{\"type\":\"config\",\"role\":\"controller\","
               "\"relay_mode\":\"%s\",\"relay_active_low\":%s,"
               "\"pulse_ms\":%u,\"cooldown_ms\":%u,"
               "\"follow_max_ms\":%u,\"key_pulse_ms\":%u,"
               "\"inactivity_s\":%lu,"
               "\"trigger_hid\":%s,\"schema\":%u,\"sequence\":%lu,"
               "\"keycodes\":[%u,%u,%u,%u,%u,%u,%u]}\r\n",
               relay_mode_name(),
               json_bool(config.relay_active_low != 0),
               config.pulse_ms,
               config.cooldown_ms,
               config.follow_max_ms,
               config.key_pulse_ms,
               (unsigned long)(config.inactivity_ms / 1000u),
               json_bool(config.trigger_hid_enabled != 0),
               CONTROLLER_FLASH_SCHEMA,
               (unsigned long)config_sequence,
               config.keycodes[0], config.keycodes[1], config.keycodes[2],
               config.keycodes[3], config.keycodes[4], config.keycodes[5],
               config.keycodes[6]);
}

static void send_status(void) {
    cdc_printf("{\"type\":\"status\",\"role\":\"controller\","
               "\"coin\":%s,\"p1_start\":%s,\"p1_trigger\":%s,"
               "\"p1_bomb\":%s,\"p2_start\":%s,\"p2_trigger\":%s,"
               "\"p2_bomb\":%s,\"p1_relay\":%s,\"p2_relay\":%s,"
               "\"p1_armed\":%s,\"p2_armed\":%s,"
               "\"maintenance\":%s,\"motion_enabled\":%s,"
               "\"motion_change_id\":%lu,\"uptime_ms\":%lu}\r\n",
               json_bool(gt_input_is_active(&inputs[INPUT_COIN])),
               json_bool(gt_input_is_active(&inputs[INPUT_P1_START])),
               json_bool(gt_input_is_active(&inputs[INPUT_P1_TRIGGER])),
               json_bool(gt_input_is_active(&inputs[INPUT_P1_BOMB])),
               json_bool(gt_input_is_active(&inputs[INPUT_P2_START])),
               json_bool(gt_input_is_active(&inputs[INPUT_P2_TRIGGER])),
               json_bool(gt_input_is_active(&inputs[INPUT_P2_BOMB])),
               json_bool(relays[0].output_on),
               json_bool(relays[1].output_on),
               json_bool(relays[0].armed),
               json_bool(relays[1].armed),
               json_bool(maintenance_mode),
               json_bool(gun_motion_enabled),
               (unsigned long)motion_change_id,
               (unsigned long)now_ms());
}

static bool equals_ignore_case(const char *left, const char *right) {
    if (left == NULL || right == NULL) {
        return false;
    }
    while (*left != '\0' && *right != '\0') {
        if (toupper((unsigned char)*left) != toupper((unsigned char)*right)) {
            return false;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

static bool parse_uint(const char *text, uint32_t min, uint32_t max, uint32_t *out) {
    if (text == NULL || *text == '\0') {
        return false;
    }
    char *end = NULL;
    const unsigned long value = strtoul(text, &end, 10);
    if (end == text || *end != '\0' || value < min || value > max) {
        return false;
    }
    *out = (uint32_t)value;
    return true;
}

static int input_index_from_name(const char *name) {
    for (size_t i = 0; i < INPUT_COUNT; ++i) {
        if (equals_ignore_case(name, input_names[i])) {
            return (int)i;
        }
    }
    return -1;
}

static uint8_t keycode_from_token(const char *token, bool *valid) {
    *valid = true;
    if (token == NULL) {
        *valid = false;
        return HID_KEY_NONE;
    }
    if (equals_ignore_case(token, "NONE")) {
        return HID_KEY_NONE;
    }
    if (token[0] == '\0' || token[1] != '\0') {
        *valid = false;
        return HID_KEY_NONE;
    }

    const char character = (char)toupper((unsigned char)token[0]);
    if (character >= 'A' && character <= 'Z') {
        return (uint8_t)(HID_KEY_A + (character - 'A'));
    }
    switch (character) {
        case '0': return HID_KEY_0;
        case '1': return HID_KEY_1;
        case '2': return HID_KEY_2;
        case '3': return HID_KEY_3;
        case '4': return HID_KEY_4;
        case '5': return HID_KEY_5;
        case '6': return HID_KEY_6;
        case '7': return HID_KEY_7;
        case '8': return HID_KEY_8;
        case '9': return HID_KEY_9;
        default:
            *valid = false;
            return HID_KEY_NONE;
    }
}

static void command_error(const char *message) {
    cdc_printf("{\"ok\":false,\"error\":\"%s\"}\r\n", message);
}

static void save_config(void) {
    ++config_sequence;
    if (gt_flash_save(CONTROLLER_FLASH_MAGIC,
                      CONTROLLER_FLASH_SCHEMA,
                      &config,
                      sizeof(config),
                      config_sequence)) {
        cdc_printf("{\"ok\":true,\"saved\":true,\"sequence\":%lu}\r\n",
                   (unsigned long)config_sequence);
    } else {
        --config_sequence;
        command_error("flash_save_failed");
    }
}

static void apply_relay_polarity_safely(void) {
    relay_all_off();
    for (unsigned player = 0; player < PLAYER_COUNT; ++player) {
        relay_configure_off_pull(player);
        gpio_put(relay_pin(player), relay_off_level());
    }
}

static void handle_set_command(char *field, char *value, char *extra) {
    uint32_t number = 0;
    if (equals_ignore_case(field, "RELAY_MODE")) {
        relay_all_off();
        if (equals_ignore_case(value, "OFF")) {
            config.relay_mode = RELAY_MODE_OFF;
        } else if (equals_ignore_case(value, "PULSE")) {
            config.relay_mode = RELAY_MODE_PULSE;
        } else if (equals_ignore_case(value, "FOLLOW")) {
            config.relay_mode = RELAY_MODE_FOLLOW;
        } else {
            command_error("invalid_relay_mode");
            return;
        }
    } else if (equals_ignore_case(field, "RELAY_ACTIVE_LOW")) {
        if (!parse_uint(value, 0, 1, &number)) {
            command_error("invalid_relay_active_low");
            return;
        }
        relay_all_off();
        config.relay_active_low = (uint8_t)number;
        apply_relay_polarity_safely();
    } else if (equals_ignore_case(field, "PULSE_MS")) {
        if (!parse_uint(value, 10, 500, &number)) {
            command_error("invalid_pulse_ms");
            return;
        }
        config.pulse_ms = (uint16_t)number;
    } else if (equals_ignore_case(field, "COOLDOWN_MS")) {
        if (!parse_uint(value, 20, 2000, &number)) {
            command_error("invalid_cooldown_ms");
            return;
        }
        config.cooldown_ms = (uint16_t)number;
    } else if (equals_ignore_case(field, "FOLLOW_MAX_MS")) {
        if (!parse_uint(value, 20, 1000, &number)) {
            command_error("invalid_follow_max_ms");
            return;
        }
        config.follow_max_ms = (uint16_t)number;
    } else if (equals_ignore_case(field, "KEY_PULSE_MS")) {
        if (!parse_uint(value, 20, 200, &number)) {
            command_error("invalid_key_pulse_ms");
            return;
        }
        config.key_pulse_ms = (uint16_t)number;
    } else if (equals_ignore_case(field, "INACTIVITY_S")) {
        if (!parse_uint(value, 0, 3600, &number)) {
            command_error("invalid_inactivity_s");
            return;
        }
        config.inactivity_ms = number * 1000u;
    } else if (equals_ignore_case(field, "TRIGGER_HID")) {
        if (!parse_uint(value, 0, 1, &number)) {
            command_error("invalid_trigger_hid");
            return;
        }
        config.trigger_hid_enabled = (uint8_t)number;
        trigger_hid_suppressed_until_release[0] =
            gt_input_is_active(&inputs[INPUT_P1_TRIGGER]);
        trigger_hid_suppressed_until_release[1] =
            gt_input_is_active(&inputs[INPUT_P2_TRIGGER]);
        keyboard_dirty = true;
    } else if (equals_ignore_case(field, "KEY")) {
        const int index = input_index_from_name(value);
        bool valid = false;
        const uint8_t keycode = keycode_from_token(extra, &valid);
        if (index < 0 || !valid) {
            command_error("invalid_key_mapping");
            return;
        }
        config.keycodes[index] = keycode;
        if (index == INPUT_P1_TRIGGER || index == INPUT_P2_TRIGGER) {
            const unsigned player = index == INPUT_P1_TRIGGER ? 0u : 1u;
            trigger_hid_suppressed_until_release[player] =
                gt_input_is_active(&inputs[(size_t)index]);
        }
        keyboard_dirty = true;
    } else {
        command_error("unknown_setting");
        return;
    }

    cdc_printf("{\"ok\":true,\"updated\":\"%s\"}\r\n", field);
    send_config();
}

static void set_maintenance_mode(bool enabled, uint32_t now) {
    maintenance_mode = enabled;
    maintenance_deadline_ms = enabled ? now + MAINTENANCE_TIMEOUT_MS : 0u;
    relay_all_off();
    for (size_t i = 0; i < INPUT_COUNT; ++i) {
        key_pulse_active[i] = false;
    }
    clear_start_command_state();
    if (gt_input_is_active(&inputs[INPUT_P1_START]) ||
        gt_input_is_active(&inputs[INPUT_P2_START])) {
        start_chord_active = true;
        start_chord_cancelled = true;
        start_chord_fired = false;
    }
    suppress_held_trigger_keys();
    keyboard_dirty = true;
    cdc_printf("{\"event\":\"maintenance\",\"enabled\":%s,"
               "\"timeout_ms\":%lu}\r\n",
               json_bool(enabled),
               (unsigned long)(enabled ? MAINTENANCE_TIMEOUT_MS : 0u));
}

static void maintenance_task(uint32_t now) {
    if (!maintenance_mode || !time_reached(now, maintenance_deadline_ms)) {
        return;
    }
    set_maintenance_mode(false, now);
    set_gun_motion_enabled(true, "maintenance_timeout");
    cdc_printf("{\"event\":\"maintenance_timeout\"}\r\n");
}

static void handle_command(const char *line) {
    char copy[CDC_LINE_MAX];
    strncpy(copy, line, sizeof(copy) - 1u);
    copy[sizeof(copy) - 1u] = '\0';

    char *command = strtok(copy, " \t");
    char *arg1 = strtok(NULL, " \t");
    char *arg2 = strtok(NULL, " \t");
    char *arg3 = strtok(NULL, " \t");

    if (command == NULL) {
        return;
    }
    if (equals_ignore_case(command, "PING")) {
        cdc_printf("{\"ok\":true,\"pong\":true}\r\n");
    } else if (equals_ignore_case(command, "INFO")) {
        send_info();
    } else if (equals_ignore_case(command, "STATUS")) {
        send_status();
    } else if (equals_ignore_case(command, "GET") &&
               equals_ignore_case(arg1, "CONFIG")) {
        send_config();
    } else if (equals_ignore_case(command, "MAINTENANCE")) {
        uint32_t enabled = 0;
        if (!parse_uint(arg1, 0, 1, &enabled)) {
            command_error("invalid_maintenance");
        } else {
            set_maintenance_mode(enabled != 0u, now_ms());
            cdc_printf("{\"ok\":true,\"maintenance\":%s}\r\n",
                       json_bool(maintenance_mode));
        }
    } else if (equals_ignore_case(command, "MOTION")) {
        uint32_t enabled = 0;
        if (!parse_uint(arg1, 0, 1, &enabled)) {
            command_error("invalid_motion");
        } else {
            set_gun_motion_enabled(enabled != 0u, "host");
            cdc_printf("{\"ok\":true,\"motion_enabled\":%s}\r\n",
                       json_bool(gun_motion_enabled));
        }
    } else if (equals_ignore_case(command, "SET")) {
        if (arg1 == NULL || arg2 == NULL) {
            command_error("missing_set_arguments");
        } else {
            handle_set_command(arg1, arg2, arg3);
        }
    } else if (equals_ignore_case(command, "SAVE")) {
        save_config();
    } else if (equals_ignore_case(command, "DEFAULTS")) {
        relay_all_off();
        config_defaults(&config);
        set_gun_motion_enabled(true, "defaults");
        apply_relay_polarity_safely();
        suppress_held_trigger_keys();
        keyboard_dirty = true;
        cdc_printf("{\"ok\":true,\"defaults\":true}\r\n");
        send_config();
    } else if (equals_ignore_case(command, "BOOTSEL")) {
        relay_all_off();
        cdc_printf("{\"ok\":true,\"bootsel\":true}\r\n");
        sleep_ms(100);
        reset_usb_boot(0, 0);
    } else if (equals_ignore_case(command, "REBOOT")) {
        relay_all_off();
        cdc_printf("{\"ok\":true,\"reboot\":true}\r\n");
        sleep_ms(100);
        watchdog_reboot(0, 0, 0);
    } else {
        command_error("unknown_command");
    }
}

static void cdc_task(void) {
    // Bound serial parsing so a command burst cannot starve USB HID reports.
    for (unsigned processed = 0; processed < 64u && tud_cdc_available(); ++processed) {
        char character = 0;
        if (tud_cdc_read(&character, 1) != 1) {
            break;
        }
        if (character == '\r') {
            continue;
        }
        if (character == '\n') {
            if (cdc_discard_until_newline) {
                cdc_discard_until_newline = false;
                cdc_line_length = 0;
                return;
            }
            cdc_line[cdc_line_length] = '\0';
            handle_command(cdc_line);
            cdc_line_length = 0;
            return;
        }
        if (cdc_discard_until_newline) {
            continue;
        }
        if (cdc_line_length + 1u < sizeof(cdc_line)) {
            cdc_line[cdc_line_length++] = character;
        } else {
            cdc_line_length = 0;
            cdc_discard_until_newline = true;
            command_error("line_too_long");
            return;
        }
    }
}

static void input_task(uint32_t now) {
    for (size_t i = 0; i < INPUT_COUNT; ++i) {
        if (!gt_input_update(&inputs[i], now)) {
            continue;
        }

        const bool active = gt_input_is_active(&inputs[i]);
        if (input_is_start(i)) {
            const unsigned start_player = start_player_from_input(i);
            if (active) {
                start_pending[start_player] = !maintenance_mode;
            } else {
                if (start_pending[start_player] && !start_chord_active &&
                    !maintenance_mode) {
                    start_key_pulse(start_player, now);
                }
                start_pending[start_player] = false;
            }
        } else if (active && !maintenance_mode && input_uses_key_pulse(i)) {
            key_pulse_active[i] = true;
            key_pulse_until_ms[i] = now + config.key_pulse_ms;
        }
        keyboard_dirty = true;
        cdc_printf("{\"event\":\"input\",\"role\":\"controller\","
                   "\"name\":\"%s\",\"active\":%s}\r\n",
                   input_names[i], json_bool(active));

        const int8_t player = input_players[i];
        if (player >= 0) {
            relay_state_t *state = &relays[(unsigned)player];
            state->last_activity_ms = now;
            if (!state->armed) {
                state->armed = true;
                cdc_printf("{\"event\":\"activity\",\"player\":%u,\"armed\":true}\r\n",
                           (unsigned)player + 1u);
            }
        }

        if (i == INPUT_P1_TRIGGER || i == INPUT_P2_TRIGGER) {
            const unsigned trigger_player = i == INPUT_P1_TRIGGER ? 0u : 1u;
            if (active) {
                if (!maintenance_mode) {
                    relay_trigger_rising(trigger_player, now);
                }
            } else {
                trigger_hid_suppressed_until_release[trigger_player] = false;
                relay_trigger_released(trigger_player, now);
            }
        }
    }
}

static void suppress_held_trigger_keys(void) {
    trigger_hid_suppressed_until_release[0] =
        gt_input_is_active(&inputs[INPUT_P1_TRIGGER]);
    trigger_hid_suppressed_until_release[1] =
        gt_input_is_active(&inputs[INPUT_P2_TRIGGER]);
}

void tud_mount_cb(void) {
    usb_mounted = true;
    suppress_held_trigger_keys();
    keyboard_dirty = true;
}

void tud_umount_cb(void) {
    usb_mounted = false;
    suppress_held_trigger_keys();
    relay_all_off();
    set_maintenance_mode(false, now_ms());
    set_gun_motion_enabled(true, "usb_disconnect");
}

void tud_suspend_cb(bool remote_wakeup_en) {
    (void)remote_wakeup_en;
    suppress_held_trigger_keys();
    relay_all_off();
    set_maintenance_mode(false, now_ms());
    set_gun_motion_enabled(true, "usb_suspend");
}

void tud_resume_cb(void) {
    keyboard_dirty = true;
}

int main(void) {
    load_config();
    watchdog_rebooted = watchdog_caused_reboot();

    const uint32_t boot_ms = now_ms();
    // Establish the configured OFF level before initializing non-critical inputs.
    // External hardware must still provide a fail-safe pull for power-loss/reset gaps.
    for (unsigned player = 0; player < PLAYER_COUNT; ++player) {
        relay_gpio_init(player);
        relays[player].armed = true;
        relays[player].last_activity_ms = boot_ms;
        relays[player].cooldown_until_ms = boot_ms;
    }
    for (size_t i = 0; i < INPUT_COUNT; ++i) {
        gt_input_init(&inputs[i], input_pins[i], true, 20, boot_ms);
    }
    suppress_held_trigger_keys();
    if (gt_input_is_active(&inputs[INPUT_P1_START]) ||
        gt_input_is_active(&inputs[INPUT_P2_START])) {
        // A stuck/held Start line during boot must not request calibration or create a
        // game Start. Require a complete release before arming the chord again.
        start_chord_active = true;
        start_chord_cancelled = true;
    }

    tusb_init();
    watchdog_enable(2000, true);

    while (true) {
        tud_task();
        cdc_task();

        const uint32_t current_ms = now_ms();
        maintenance_task(current_ms);
        motion_timeout_task(current_ms);
        input_task(current_ms);
        start_chord_task(current_ms);
        relay_update(current_ms);
        keyboard_task(current_ms);

        const bool cdc_connected = tud_cdc_connected();
        if (cdc_connected && !last_cdc_connected) {
            send_info();
            send_config();
            send_status();
        }
        last_cdc_connected = cdc_connected;

        if (cdc_connected && (uint32_t)(current_ms - last_status_ms) >= 500u) {
            last_status_ms = current_ms;
            send_status();
        }

        watchdog_update();
        sleep_ms(1);
    }
}
