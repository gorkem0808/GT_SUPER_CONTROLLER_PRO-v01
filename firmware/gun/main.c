#include <ctype.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "flash_store.h"
#include "hardware/adc.h"
#include "hardware/watchdog.h"
#include "pico/bootrom.h"
#include "pico/stdlib.h"
#include "tusb.h"

#ifndef GT_FIRMWARE_VERSION
#define GT_FIRMWARE_VERSION "dev"
#endif
#ifndef GT_GUN_PLAYER
#error GT_GUN_PLAYER must be defined
#endif
#ifndef GT_GUN_PRODUCT
#define GT_GUN_PRODUCT "GT GUN"
#endif

#define GUN_FLASH_SCHEMA 2u
#define GUN_FLASH_SCHEMA_LEGACY 1u
#define GUN_FLASH_MAGIC_BASE 0x47544730u
#define GUN_FLASH_MAGIC (GUN_FLASH_MAGIC_BASE + GT_GUN_PLAYER)
#define PIN_ADC_X 26u
#define PIN_ADC_Y 27u
#define ADC_INPUT_X 0u
#define ADC_INPUT_Y 1u
#define CDC_LINE_MAX 192u
#define HID_MAX 32767
#define CAL_POINT_COUNT 4u
#define CAL_SAMPLE_COUNT 25u
#define CAL_TRIM_COUNT 8u
#define CAL_MAX_CAPTURE_SPREAD 90u
#define CALIBRATION_TIMEOUT_MS 120000u
#define MOTION_DISABLE_TIMEOUT_MS 180000u
#define CAL_MIN_AXIS_SPAN 240
#define CAL_MIN_EDGE_SPAN 160

typedef enum {
    CAL_TL = 0,
    CAL_TR,
    CAL_BR,
    CAL_BL,
} calibration_point_t;

typedef enum {
    CAL_RESULT_OK = 0,
    CAL_RESULT_RANGE_TOO_SMALL,
    CAL_RESULT_WRONG_ORDER,
} calibration_result_t;

typedef struct {
    uint16_t value;
    uint16_t spread;
} adc_capture_t;

typedef struct {
    adc_capture_t x;
    adc_capture_t y;
} calibration_capture_t;

typedef struct {
    uint16_t cal_x[CAL_POINT_COUNT];
    uint16_t cal_y[CAL_POINT_COUNT];
    uint16_t x_left;
    uint16_t x_right;
    uint16_t y_top;
    uint16_t y_bottom;
    uint16_t report_threshold;
    uint8_t filter_percent;
    uint8_t overscan_percent;
    uint8_t invert_x;
    uint8_t invert_y;
    uint8_t mouse_button_enabled;
    uint8_t calibrated;
    uint8_t reserved[10];
} gun_config_t;

_Static_assert(sizeof(gun_config_t) <= 96, "Gun config too large");

typedef struct __attribute__((packed)) {
    uint8_t buttons;
    uint16_t x;
    uint16_t y;
} absolute_mouse_report_t;

_Static_assert(sizeof(absolute_mouse_report_t) == 5, "Unexpected HID report size");

static gun_config_t config;
static gun_config_t calibration_backup;
static uint32_t config_sequence;
static bool watchdog_rebooted;
static bool usb_mounted;
static bool stream_enabled = true;
static bool motion_enabled = true;
static uint32_t motion_disable_deadline_ms;
static bool calibrating;
static uint8_t calibration_index;
static uint32_t calibration_deadline_ms;
static uint16_t calibration_spread_x[CAL_POINT_COUNT];
static uint16_t calibration_spread_y[CAL_POINT_COUNT];
static uint16_t raw_x;
static uint16_t raw_y;
static int32_t mapped_x;
static int32_t mapped_y;
static int32_t filtered_x;
static int32_t filtered_y;
static bool filter_initialized;
static bool force_hid_report = true;
static bool previous_mouse_enabled;
static uint16_t last_sent_x;
static uint16_t last_sent_y;
static uint32_t last_hid_poll_ms;
static uint32_t last_report_ms;
static uint32_t last_adc_ms;
static uint32_t last_status_ms;
static bool last_cdc_connected;
static char cdc_line[CDC_LINE_MAX];
static size_t cdc_line_length;
static bool cdc_discard_until_newline;

static uint32_t now_ms(void) {
    return (uint32_t)(time_us_64() / 1000u);
}

static bool time_reached(uint32_t now, uint32_t deadline) {
    return (int32_t)(now - deadline) >= 0;
}

static const char *json_bool(bool value) {
    return value ? "true" : "false";
}

static const char *calibration_point_name(uint8_t index) {
    static const char *const names[CAL_POINT_COUNT] = {"TL", "TR", "BR", "BL"};
    return index < CAL_POINT_COUNT ? names[index] : "DONE";
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

static void config_defaults(gun_config_t *out) {
    memset(out, 0, sizeof(*out));
    out->x_left = 200;
    out->x_right = 3895;
    out->y_top = 200;
    out->y_bottom = 3895;
    out->report_threshold = 8;
    out->filter_percent = 35;
    out->overscan_percent = 2;
    out->invert_x = 0;
    out->invert_y = 0;
    // Trigger buttons are wired to the Controller Pico. Gun Picos only report
    // absolute X/Y position and therefore never emit mouse-button reports.
    out->mouse_button_enabled = 0;
    out->calibrated = 0;
}

static bool config_valid(const gun_config_t *candidate) {
    if (candidate->filter_percent > 95 || candidate->overscan_percent > 20 ||
        candidate->report_threshold > 2000 || candidate->invert_x > 1 ||
        candidate->invert_y > 1 || candidate->mouse_button_enabled > 1 ||
        candidate->calibrated > 1) {
        return false;
    }
    if (abs((int)candidate->x_right - (int)candidate->x_left) < 100 ||
        abs((int)candidate->y_bottom - (int)candidate->y_top) < 100) {
        return false;
    }
    return true;
}

static void load_config(void) {
    gun_config_t loaded;
    uint32_t sequence = 0;
    if (gt_flash_load(GUN_FLASH_MAGIC,
                      GUN_FLASH_SCHEMA,
                      &loaded,
                      sizeof(loaded),
                      &sequence) &&
        config_valid(&loaded)) {
        config = loaded;
        config.mouse_button_enabled = 0;
        config_sequence = sequence;
        return;
    }

    // Preserve existing four-corner calibration while migrating away from the
    // legacy local trigger/GP19 architecture. The compatibility field is always
    // cleared and is ignored by HID reporting in schema 2.
    if (gt_flash_load(GUN_FLASH_MAGIC,
                      GUN_FLASH_SCHEMA_LEGACY,
                      &loaded,
                      sizeof(loaded),
                      &sequence) &&
        config_valid(&loaded)) {
        config = loaded;
        config.mouse_button_enabled = 0;
        config_sequence = sequence;
        return;
    }

    config_defaults(&config);
    config_sequence = 0;
}

static bool save_config_internal(void) {
    const uint32_t next_sequence = config_sequence + 1u;
    if (!gt_flash_save(GUN_FLASH_MAGIC,
                       GUN_FLASH_SCHEMA,
                       &config,
                       sizeof(config),
                       next_sequence)) {
        return false;
    }
    config_sequence = next_sequence;
    return true;
}

static uint16_t adc_read_samples(uint8_t input, unsigned sample_count) {
    adc_select_input(input);
    // Discard the first conversion after switching the ADC multiplexer.
    (void)adc_read();
    uint32_t sum = 0;
    for (unsigned sample = 0; sample < sample_count; ++sample) {
        sum += adc_read();
    }
    return (uint16_t)((sum + sample_count / 2u) / sample_count);
}

static uint16_t adc_read_average(uint8_t input) {
    return adc_read_samples(input, 8u);
}

static void sort_u16(uint16_t *samples, size_t count) {
    for (size_t i = 1; i < count; ++i) {
        const uint16_t value = samples[i];
        size_t position = i;
        while (position > 0 && samples[position - 1u] > value) {
            samples[position] = samples[position - 1u];
            --position;
        }
        samples[position] = value;
    }
}

static adc_capture_t trimmed_capture(uint16_t samples[CAL_SAMPLE_COUNT]) {
    sort_u16(samples, CAL_SAMPLE_COUNT);

    const size_t first = CAL_TRIM_COUNT;
    const size_t last = CAL_SAMPLE_COUNT - CAL_TRIM_COUNT;
    uint32_t sum = 0;
    for (size_t i = first; i < last; ++i) {
        sum += samples[i];
    }
    const size_t used = last - first;
    adc_capture_t capture = {
        .value = (uint16_t)((sum + used / 2u) / used),
        .spread = (uint16_t)(samples[last - 1u] - samples[first]),
    };
    return capture;
}

static calibration_capture_t adc_capture_calibration_point(void) {
    uint16_t x_samples[CAL_SAMPLE_COUNT];
    uint16_t y_samples[CAL_SAMPLE_COUNT];

    // Capture both axes over the same short time window. This rejects a point
    // when the gun is still moving during the trigger press instead of only
    // measuring instantaneous electrical noise.
    for (size_t i = 0; i < CAL_SAMPLE_COUNT; ++i) {
        adc_select_input(ADC_INPUT_X);
        (void)adc_read();
        x_samples[i] = adc_read();

        adc_select_input(ADC_INPUT_Y);
        (void)adc_read();
        y_samples[i] = adc_read();

        if (i + 1u < CAL_SAMPLE_COUNT) {
            sleep_us(400);
        }
    }

    calibration_capture_t capture = {
        .x = trimmed_capture(x_samples),
        .y = trimmed_capture(y_samples),
    };
    return capture;
}

static int32_t clamp_hid(int32_t value) {
    if (value < 0) {
        return 0;
    }
    if (value > HID_MAX) {
        return HID_MAX;
    }
    return value;
}

static int32_t map_axis(uint16_t raw,
                        uint16_t first,
                        uint16_t second,
                        bool invert,
                        uint8_t overscan_percent) {
    const int32_t denominator = (int32_t)second - (int32_t)first;
    if (abs(denominator) < 100) {
        return HID_MAX / 2;
    }

    int64_t mapped = ((int64_t)((int32_t)raw - (int32_t)first) * HID_MAX) /
                     denominator;
    if (invert) {
        mapped = HID_MAX - mapped;
    }

    if (overscan_percent > 0 && overscan_percent < 50) {
        const int32_t divisor = 100 - 2 * (int32_t)overscan_percent;
        mapped = (mapped * 100 - (int64_t)overscan_percent * HID_MAX) / divisor;
    }
    return clamp_hid((int32_t)mapped);
}

static void update_mapping(void) {
    mapped_x = map_axis(raw_x,
                        config.x_left,
                        config.x_right,
                        config.invert_x != 0,
                        config.overscan_percent);
    mapped_y = map_axis(raw_y,
                        config.y_top,
                        config.y_bottom,
                        config.invert_y != 0,
                        config.overscan_percent);

    if (!filter_initialized) {
        filtered_x = mapped_x;
        filtered_y = mapped_y;
        filter_initialized = true;
        return;
    }

    const int32_t old_weight = config.filter_percent;
    const int32_t new_weight = 100 - old_weight;
    filtered_x = (filtered_x * old_weight + mapped_x * new_weight + 50) / 100;
    filtered_y = (filtered_y * old_weight + mapped_y * new_weight + 50) / 100;
}

static bool mouse_enabled(void) {
    return motion_enabled && !calibrating;
}

static void hid_task(uint32_t current_ms) {
    if (!usb_mounted || !tud_hid_ready() ||
        (uint32_t)(current_ms - last_hid_poll_ms) < 8u) {
        return;
    }
    last_hid_poll_ms = current_ms;

    const bool enabled = mouse_enabled();
    if (enabled != previous_mouse_enabled) {
        previous_mouse_enabled = enabled;
        force_hid_report = true;
    }

    const uint16_t x = (uint16_t)clamp_hid(filtered_x);
    const uint16_t y = (uint16_t)clamp_hid(filtered_y);

    if (!enabled) {
        force_hid_report = false;
        return;
    }

    const bool moved = abs((int)x - (int)last_sent_x) >= config.report_threshold ||
                       abs((int)y - (int)last_sent_y) >= config.report_threshold;
    const bool keepalive = (uint32_t)(current_ms - last_report_ms) >= 100u;
    if (!force_hid_report && !moved && !keepalive) {
        return;
    }

    absolute_mouse_report_t report = {
        .buttons = 0,
        .x = x,
        .y = y,
    };
    if (tud_hid_report(0, &report, sizeof(report))) {
        last_sent_x = x;
        last_sent_y = y;
        force_hid_report = false;
        last_report_ms = current_ms;
    }
}

static void send_info(void) {
    cdc_printf("{\"type\":\"info\",\"role\":\"gun\",\"player\":%d,"
               "\"name\":\"%s\",\"version\":\"%s\",\"protocol\":3,"
               "\"watchdog_reboot\":%s}\r\n",
               GT_GUN_PLAYER,
               GT_GUN_PRODUCT,
               GT_FIRMWARE_VERSION,
               json_bool(watchdog_rebooted));
}

static uint16_t calibration_x_span(const gun_config_t *candidate) {
    return (uint16_t)abs((int)candidate->x_right - (int)candidate->x_left);
}

static uint16_t calibration_y_span(const gun_config_t *candidate) {
    return (uint16_t)abs((int)candidate->y_bottom - (int)candidate->y_top);
}

static uint8_t calibration_quality(const gun_config_t *candidate, bool include_noise) {
    if (candidate->calibrated == 0) {
        return 0;
    }

    const uint32_t x_span = calibration_x_span(candidate);
    const uint32_t y_span = calibration_y_span(candidate);
    const uint32_t scale = x_span + y_span;
    if (scale == 0u) {
        return 0;
    }

    const uint32_t edge_error =
        (uint32_t)abs((int)candidate->cal_x[CAL_TL] - (int)candidate->cal_x[CAL_BL]) +
        (uint32_t)abs((int)candidate->cal_x[CAL_TR] - (int)candidate->cal_x[CAL_BR]) +
        (uint32_t)abs((int)candidate->cal_y[CAL_TL] - (int)candidate->cal_y[CAL_TR]) +
        (uint32_t)abs((int)candidate->cal_y[CAL_BL] - (int)candidate->cal_y[CAL_BR]);

    uint32_t penalty = (edge_error * 45u) / (2u * scale);
    if (penalty > 40u) {
        penalty = 40u;
    }

    if (include_noise) {
        uint32_t noise = 0;
        for (size_t i = 0; i < CAL_POINT_COUNT; ++i) {
            noise += calibration_spread_x[i] + calibration_spread_y[i];
        }
        uint32_t noise_penalty = (noise * 40u) / scale;
        if (noise_penalty > 20u) {
            noise_penalty = 20u;
        }
        penalty += noise_penalty;
    }

    if (penalty > 60u) {
        penalty = 60u;
    }
    return (uint8_t)(100u - penalty);
}

static uint8_t stored_quality(void) {
    if (config.calibrated == 0) {
        return 0;
    }
    return config.reserved[0] != 0u ? config.reserved[0]
                                     : calibration_quality(&config, false);
}

static void send_config(void) {
    cdc_printf("{\"type\":\"config\",\"role\":\"gun\",\"player\":%d,"
               "\"calibrated\":%s,\"x_left\":%u,\"x_right\":%u,"
               "\"y_top\":%u,\"y_bottom\":%u,\"filter\":%u,"
               "\"threshold\":%u,\"overscan\":%u,\"invert_x\":%s,"
               "\"invert_y\":%s,\"button\":false,\"schema\":%u,"
               "\"sequence\":%lu,\"quality\":%u,"
               "\"x_span\":%u,\"y_span\":%u,"
               "\"cal_x\":[%u,%u,%u,%u],\"cal_y\":[%u,%u,%u,%u]}\r\n",
               GT_GUN_PLAYER,
               json_bool(config.calibrated != 0),
               config.x_left,
               config.x_right,
               config.y_top,
               config.y_bottom,
               config.filter_percent,
               config.report_threshold,
               config.overscan_percent,
               json_bool(config.invert_x != 0),
               json_bool(config.invert_y != 0),
               GUN_FLASH_SCHEMA,
               (unsigned long)config_sequence,
               stored_quality(),
               calibration_x_span(&config),
               calibration_y_span(&config),
               config.cal_x[0], config.cal_x[1], config.cal_x[2], config.cal_x[3],
               config.cal_y[0], config.cal_y[1], config.cal_y[2], config.cal_y[3]);
}

static void send_status(void) {
    cdc_printf("{\"type\":\"status\",\"role\":\"gun\",\"player\":%d,"
               "\"raw_x\":%u,\"raw_y\":%u,\"x\":%ld,\"y\":%ld,"
               "\"enabled\":%s,\"motion_enabled\":%s,"
               "\"calibrated\":%s,\"quality\":%u,"
               "\"calibrating\":%s,\"next_point\":\"%s\","
               "\"uptime_ms\":%lu}\r\n",
               GT_GUN_PLAYER,
               raw_x,
               raw_y,
               (long)filtered_x,
               (long)filtered_y,
               json_bool(mouse_enabled()),
               json_bool(motion_enabled),
               json_bool(config.calibrated != 0),
               stored_quality(),
               json_bool(calibrating),
               calibrating ? calibration_point_name(calibration_index) : "NONE",
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

static void command_error(const char *message) {
    cdc_printf("{\"ok\":false,\"role\":\"gun\",\"player\":%d,"
               "\"error\":\"%s\"}\r\n",
               GT_GUN_PLAYER,
               message);
}

static calibration_result_t calculate_calibration(uint8_t *quality_out,
                                                  uint16_t *x_span_out,
                                                  uint16_t *y_span_out) {
    const int32_t top_dx = (int32_t)config.cal_x[CAL_TR] - (int32_t)config.cal_x[CAL_TL];
    const int32_t bottom_dx = (int32_t)config.cal_x[CAL_BR] - (int32_t)config.cal_x[CAL_BL];
    const int32_t left_dy = (int32_t)config.cal_y[CAL_BL] - (int32_t)config.cal_y[CAL_TL];
    const int32_t right_dy = (int32_t)config.cal_y[CAL_BR] - (int32_t)config.cal_y[CAL_TR];

    if (abs(top_dx) < CAL_MIN_EDGE_SPAN || abs(bottom_dx) < CAL_MIN_EDGE_SPAN ||
        abs(left_dy) < CAL_MIN_EDGE_SPAN || abs(right_dy) < CAL_MIN_EDGE_SPAN) {
        return CAL_RESULT_RANGE_TOO_SMALL;
    }
    if ((top_dx > 0) != (bottom_dx > 0) ||
        (left_dy > 0) != (right_dy > 0)) {
        return CAL_RESULT_WRONG_ORDER;
    }

    const uint16_t x_left = (uint16_t)((config.cal_x[CAL_TL] +
                                        config.cal_x[CAL_BL] + 1u) /
                                       2u);
    const uint16_t x_right = (uint16_t)((config.cal_x[CAL_TR] +
                                         config.cal_x[CAL_BR] + 1u) /
                                        2u);
    const uint16_t y_top = (uint16_t)((config.cal_y[CAL_TL] +
                                       config.cal_y[CAL_TR] + 1u) /
                                      2u);
    const uint16_t y_bottom = (uint16_t)((config.cal_y[CAL_BR] +
                                          config.cal_y[CAL_BL] + 1u) /
                                         2u);

    const uint16_t x_span = (uint16_t)abs((int)x_right - (int)x_left);
    const uint16_t y_span = (uint16_t)abs((int)y_bottom - (int)y_top);
    if (x_span < CAL_MIN_AXIS_SPAN || y_span < CAL_MIN_AXIS_SPAN) {
        return CAL_RESULT_RANGE_TOO_SMALL;
    }

    config.x_left = x_left;
    config.x_right = x_right;
    config.y_top = y_top;
    config.y_bottom = y_bottom;
    config.calibrated = 1;
    const uint8_t quality = calibration_quality(&config, true);
    config.reserved[0] = quality;
    filter_initialized = false;

    if (quality_out != NULL) {
        *quality_out = quality;
    }
    if (x_span_out != NULL) {
        *x_span_out = x_span;
    }
    if (y_span_out != NULL) {
        *y_span_out = y_span;
    }
    return CAL_RESULT_OK;
}

static void calibration_error(const char *error) {
    cdc_printf("{\"event\":\"cal_error\",\"role\":\"gun\",\"player\":%d,"
               "\"error\":\"%s\"}\r\n",
               GT_GUN_PLAYER,
               error);
}

static void calibration_start(void) {
    if (calibrating) {
        calibration_error("calibration_busy");
        return;
    }

    calibration_backup = config;
    calibrating = true;
    calibration_deadline_ms = now_ms() + CALIBRATION_TIMEOUT_MS;
    calibration_index = 0;
    memset(calibration_spread_x, 0, sizeof(calibration_spread_x));
    memset(calibration_spread_y, 0, sizeof(calibration_spread_y));
    force_hid_report = true;
    cdc_printf("{\"ok\":true,\"role\":\"gun\",\"calibration\":\"started\",\"player\":%d}\r\n",
               GT_GUN_PLAYER);
    cdc_printf("{\"event\":\"cal_ready\",\"role\":\"gun\",\"player\":%d,\"point\":\"TL\"}\r\n",
               GT_GUN_PLAYER);
}

static void calibration_restore_previous(void) {
    if (calibrating) {
        config = calibration_backup;
    }
    calibrating = false;
    calibration_deadline_ms = 0;
    calibration_index = 0;
    filter_initialized = false;
    force_hid_report = true;
}

static void calibration_cancel(void) {
    calibration_restore_previous();
    cdc_printf("{\"ok\":true,\"role\":\"gun\",\"calibration\":\"cancelled\",\"player\":%d}\r\n",
               GT_GUN_PLAYER);
    cdc_printf("{\"event\":\"cal_cancelled\",\"role\":\"gun\",\"player\":%d}\r\n",
               GT_GUN_PLAYER);
}

static void calibration_timeout_task(uint32_t current_ms) {
    if (!calibrating || !time_reached(current_ms, calibration_deadline_ms)) {
        return;
    }
    calibration_restore_previous();
    calibration_error("timeout");
}

static void calibration_capture(void) {
    if (!calibrating || calibration_index >= CAL_POINT_COUNT) {
        return;
    }

    const uint8_t captured = calibration_index;
    calibration_deadline_ms = now_ms() + CALIBRATION_TIMEOUT_MS;
    const calibration_capture_t capture = adc_capture_calibration_point();
    raw_x = capture.x.value;
    raw_y = capture.y.value;

    if (capture.x.spread > CAL_MAX_CAPTURE_SPREAD ||
        capture.y.spread > CAL_MAX_CAPTURE_SPREAD) {
        cdc_printf("{\"event\":\"cal_retry\",\"role\":\"gun\",\"player\":%d,"
                   "\"point\":\"%s\",\"reason\":\"unstable\"}\r\n",
                   GT_GUN_PLAYER,
                   calibration_point_name(captured));
        return;
    }

    config.cal_x[captured] = capture.x.value;
    config.cal_y[captured] = capture.y.value;
    calibration_spread_x[captured] = capture.x.spread;
    calibration_spread_y[captured] = capture.y.spread;
    cdc_printf("{\"event\":\"cal_point\",\"role\":\"gun\",\"player\":%d,\"point\":\"%s\","
               "\"raw_x\":%u,\"raw_y\":%u}\r\n",
               GT_GUN_PLAYER,
               calibration_point_name(captured),
               capture.x.value,
               capture.y.value);

    ++calibration_index;
    if (calibration_index < CAL_POINT_COUNT) {
        cdc_printf("{\"event\":\"cal_ready\",\"role\":\"gun\",\"player\":%d,\"point\":\"%s\"}\r\n",
                   GT_GUN_PLAYER,
                   calibration_point_name(calibration_index));
        return;
    }

    calibrating = false;
    calibration_deadline_ms = 0;
    uint8_t quality = 0;
    uint16_t x_span = 0;
    uint16_t y_span = 0;
    const calibration_result_t result =
        calculate_calibration(&quality, &x_span, &y_span);
    if (result != CAL_RESULT_OK) {
        config = calibration_backup;
        filter_initialized = false;
        force_hid_report = true;
        calibration_error(result == CAL_RESULT_WRONG_ORDER
                              ? "wrong_order"
                              : "range_too_small");
        return;
    }

    if (!save_config_internal()) {
        config = calibration_backup;
        filter_initialized = false;
        force_hid_report = true;
        calibration_error("flash_save_failed");
        return;
    }

    force_hid_report = true;
    cdc_printf("{\"event\":\"cal_complete\",\"role\":\"gun\",\"player\":%d,"
               "\"saved\":true,\"quality\":%u,\"x_span\":%u,\"y_span\":%u,"
               "\"x_left\":%u,\"x_right\":%u,"
               "\"y_top\":%u,\"y_bottom\":%u}\r\n",
               GT_GUN_PLAYER,
               quality,
               x_span,
               y_span,
               config.x_left,
               config.x_right,
               config.y_top,
               config.y_bottom);
    send_config();
}

static void handle_set_command(char *field, char *value) {
    uint32_t number = 0;
    if (equals_ignore_case(field, "FILTER")) {
        if (!parse_uint(value, 0, 95, &number)) {
            command_error("invalid_filter");
            return;
        }
        config.filter_percent = (uint8_t)number;
        filter_initialized = false;
    } else if (equals_ignore_case(field, "THRESHOLD")) {
        if (!parse_uint(value, 0, 2000, &number)) {
            command_error("invalid_threshold");
            return;
        }
        config.report_threshold = (uint16_t)number;
    } else if (equals_ignore_case(field, "OVERSCAN")) {
        if (!parse_uint(value, 0, 20, &number)) {
            command_error("invalid_overscan");
            return;
        }
        config.overscan_percent = (uint8_t)number;
        filter_initialized = false;
    } else if (equals_ignore_case(field, "INVERT_X")) {
        if (!parse_uint(value, 0, 1, &number)) {
            command_error("invalid_invert_x");
            return;
        }
        config.invert_x = (uint8_t)number;
        filter_initialized = false;
    } else if (equals_ignore_case(field, "INVERT_Y")) {
        if (!parse_uint(value, 0, 1, &number)) {
            command_error("invalid_invert_y");
            return;
        }
        config.invert_y = (uint8_t)number;
        filter_initialized = false;
    } else if (equals_ignore_case(field, "BUTTON")) {
        if (!parse_uint(value, 0, 1, &number)) {
            command_error("invalid_button");
            return;
        }
        // Kept as a compatibility command for older desktop builds. Trigger
        // switches now live exclusively on the Controller Pico.
        config.mouse_button_enabled = 0;
    } else {
        command_error("unknown_setting");
        return;
    }

    force_hid_report = true;
    cdc_printf("{\"ok\":true,\"updated\":\"%s\"}\r\n", field);
    send_config();
}

static void set_motion_enabled(bool enabled, const char *source) {
    const bool changed = motion_enabled != enabled;
    motion_enabled = enabled;
    motion_disable_deadline_ms =
        enabled ? 0u : now_ms() + MOTION_DISABLE_TIMEOUT_MS;
    if (enabled && changed) {
        // Reinitialize at the gun's current position. This avoids reusing a
        // stale filtered coordinate after a long disabled period.
        filter_initialized = false;
    }
    force_hid_report = enabled;
    cdc_printf("{\"event\":\"motion_state\",\"role\":\"gun\","
               "\"player\":%d,\"enabled\":%s,\"source\":\"%s\"}\r\n",
               GT_GUN_PLAYER,
               json_bool(enabled),
               source != NULL ? source : "unknown");
}

static void motion_timeout_task(uint32_t current_ms) {
    if (motion_enabled || motion_disable_deadline_ms == 0u ||
        !time_reached(current_ms, motion_disable_deadline_ms)) {
        return;
    }
    set_motion_enabled(true, "motion_timeout");
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
    } else if (equals_ignore_case(command, "STREAM")) {
        uint32_t enabled = 0;
        if (!parse_uint(arg1, 0, 1, &enabled)) {
            command_error("invalid_stream");
        } else {
            stream_enabled = enabled != 0;
            cdc_printf("{\"ok\":true,\"stream\":%s}\r\n",
                       json_bool(stream_enabled));
        }
    } else if (equals_ignore_case(command, "MOTION")) {
        uint32_t enabled = 0;
        if (!parse_uint(arg1, 0, 1, &enabled)) {
            command_error("invalid_motion");
        } else {
            set_motion_enabled(enabled != 0u, "host");
            cdc_printf("{\"ok\":true,\"motion_enabled\":%s}\r\n",
                       json_bool(motion_enabled));
        }
    } else if (equals_ignore_case(command, "SET")) {
        if (arg1 == NULL || arg2 == NULL) {
            command_error("missing_set_arguments");
        } else {
            handle_set_command(arg1, arg2);
        }
    } else if (equals_ignore_case(command, "APPLY")) {
        uint32_t overscan = 0;
        uint32_t invert_x = 0;
        uint32_t invert_y = 0;
        if (!parse_uint(arg1, 0, 20, &overscan) ||
            !parse_uint(arg2, 0, 1, &invert_x) ||
            !parse_uint(arg3, 0, 1, &invert_y)) {
            command_error("invalid_apply_arguments");
        } else {
            const gun_config_t previous = config;
            config.overscan_percent = (uint8_t)overscan;
            config.invert_x = (uint8_t)invert_x;
            config.invert_y = (uint8_t)invert_y;
            filter_initialized = false;
            force_hid_report = true;
            if (!save_config_internal()) {
                config = previous;
                filter_initialized = false;
                force_hid_report = true;
                command_error("flash_save_failed");
            } else {
                cdc_printf("{\"ok\":true,\"role\":\"gun\",\"player\":%d,"
                           "\"saved\":true,\"profile\":true,"
                           "\"sequence\":%lu}\r\n",
                           GT_GUN_PLAYER,
                           (unsigned long)config_sequence);
                send_config();
            }
        }
    } else if (equals_ignore_case(command, "CAL")) {
        if (equals_ignore_case(arg1, "START")) {
            calibration_start();
        } else if (equals_ignore_case(arg1, "CAPTURE")) {
            if (!calibrating) {
                command_error("calibration_not_active");
            } else {
                calibration_capture();
            }
        } else if (equals_ignore_case(arg1, "CANCEL")) {
            calibration_cancel();
        } else if (equals_ignore_case(arg1, "RESET")) {
            const gun_config_t previous = config;
            calibrating = false;
            calibration_deadline_ms = 0;
            calibration_index = 0;
            config.calibrated = 0;
            config.reserved[0] = 0;
            config.x_left = 200;
            config.x_right = 3895;
            config.y_top = 200;
            config.y_bottom = 3895;
            memset(config.cal_x, 0, sizeof(config.cal_x));
            memset(config.cal_y, 0, sizeof(config.cal_y));
            filter_initialized = false;
            force_hid_report = true;
            if (!save_config_internal()) {
                config = previous;
                command_error("flash_save_failed");
                calibration_error("flash_save_failed");
                send_config();
                return;
            }
            cdc_printf("{\"ok\":true,\"role\":\"gun\",\"calibration\":\"reset\",\"player\":%d}\r\n",
                       GT_GUN_PLAYER);
            cdc_printf("{\"event\":\"cal_reset\",\"role\":\"gun\",\"player\":%d}\r\n",
                       GT_GUN_PLAYER);
            send_config();
        } else {
            command_error("invalid_cal_command");
        }
    } else if (equals_ignore_case(command, "SAVE")) {
        if (save_config_internal()) {
            cdc_printf("{\"ok\":true,\"role\":\"gun\",\"player\":%d,"
                       "\"saved\":true,\"sequence\":%lu}\r\n",
                       GT_GUN_PLAYER,
                       (unsigned long)config_sequence);
        } else {
            command_error("flash_save_failed");
        }
    } else if (equals_ignore_case(command, "DEFAULTS")) {
        calibrating = false;
        calibration_deadline_ms = 0;
        calibration_index = 0;
        config_defaults(&config);
        filter_initialized = false;
        force_hid_report = true;
        cdc_printf("{\"ok\":true,\"defaults\":true}\r\n");
        send_config();
    } else if (equals_ignore_case(command, "BOOTSEL")) {
        cdc_printf("{\"ok\":true,\"bootsel\":true}\r\n");
        sleep_ms(100);
        reset_usb_boot(0, 0);
    } else if (equals_ignore_case(command, "REBOOT")) {
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

static void adc_task(uint32_t current_ms) {
    if ((uint32_t)(current_ms - last_adc_ms) < 2u) {
        return;
    }
    last_adc_ms = current_ms;
    raw_x = adc_read_average(ADC_INPUT_X);
    raw_y = adc_read_average(ADC_INPUT_Y);
    update_mapping();
}

void tud_mount_cb(void) {
    usb_mounted = true;
    force_hid_report = true;
}

void tud_umount_cb(void) {
    usb_mounted = false;
    calibration_restore_previous();
    set_motion_enabled(true, "usb_disconnect");
}

void tud_suspend_cb(bool remote_wakeup_en) {
    (void)remote_wakeup_en;
    calibration_restore_previous();
    set_motion_enabled(true, "usb_suspend");
    force_hid_report = true;
}

void tud_resume_cb(void) {
    force_hid_report = true;
}

int main(void) {
    load_config();
    watchdog_rebooted = watchdog_caused_reboot();

    adc_init();
    adc_gpio_init(PIN_ADC_X);
    adc_gpio_init(PIN_ADC_Y);

    raw_x = adc_read_average(ADC_INPUT_X);
    raw_y = adc_read_average(ADC_INPUT_Y);
    update_mapping();
    previous_mouse_enabled = mouse_enabled();

    tusb_init();
    watchdog_enable(2000, true);

    while (true) {
        tud_task();
        cdc_task();

        const uint32_t current_ms = now_ms();
        adc_task(current_ms);
        calibration_timeout_task(current_ms);
        motion_timeout_task(current_ms);
        hid_task(current_ms);

        const bool cdc_connected = tud_cdc_connected();
        if (cdc_connected && !last_cdc_connected) {
            send_info();
            send_config();
            send_status();
        }
        last_cdc_connected = cdc_connected;

        if (cdc_connected && stream_enabled &&
            (uint32_t)(current_ms - last_status_ms) >= 250u) {
            last_status_ms = current_ms;
            send_status();
        }

        watchdog_update();
        sleep_ms(1);
    }
}
