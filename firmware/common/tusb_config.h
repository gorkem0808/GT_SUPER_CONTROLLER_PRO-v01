#ifndef GT_SUPER_CONTROLLER_TUSB_CONFIG_H
#define GT_SUPER_CONTROLLER_TUSB_CONFIG_H

/*
 * GT SUPER CONTROLLER - TinyUSB configuration
 * Raspberry Pi Pico / RP2040
 * USB composite device: CDC serial + HID
 * Compatible with Pico SDK 2.3.0.
 */

#ifdef __cplusplus
extern "C" {
#endif

/* Pico SDK may already provide some of these macros on the command line. */
#ifndef CFG_TUSB_MCU
#define CFG_TUSB_MCU OPT_MCU_RP2040
#endif

#ifndef CFG_TUSB_OS
#define CFG_TUSB_OS OPT_OS_PICO
#endif

#ifndef CFG_TUSB_RHPORT0_MODE
#define CFG_TUSB_RHPORT0_MODE (OPT_MODE_DEVICE | OPT_MODE_FULL_SPEED)
#endif

#ifndef CFG_TUSB_MEM_SECTION
#define CFG_TUSB_MEM_SECTION
#endif

#ifndef CFG_TUSB_MEM_ALIGN
#define CFG_TUSB_MEM_ALIGN __attribute__((aligned(4)))
#endif

/* Device stack */
#ifndef CFG_TUD_ENABLED
#define CFG_TUD_ENABLED 1
#endif

#ifndef CFG_TUD_MAX_SPEED
#define CFG_TUD_MAX_SPEED OPT_MODE_FULL_SPEED
#endif

#ifndef CFG_TUD_ENDPOINT0_SIZE
#define CFG_TUD_ENDPOINT0_SIZE 64
#endif

/* Enabled USB classes: one CDC port and one HID interface. */
#ifndef CFG_TUD_CDC
#define CFG_TUD_CDC 1
#endif

#ifndef CFG_TUD_HID
#define CFG_TUD_HID 1
#endif

#ifndef CFG_TUD_MSC
#define CFG_TUD_MSC 0
#endif

#ifndef CFG_TUD_MIDI
#define CFG_TUD_MIDI 0
#endif

#ifndef CFG_TUD_VENDOR
#define CFG_TUD_VENDOR 0
#endif

#ifndef CFG_TUD_AUDIO
#define CFG_TUD_AUDIO 0
#endif

#ifndef CFG_TUD_VIDEO
#define CFG_TUD_VIDEO 0
#endif

/* CDC buffers */
#ifndef CFG_TUD_CDC_RX_BUFSIZE
#define CFG_TUD_CDC_RX_BUFSIZE 256
#endif

#ifndef CFG_TUD_CDC_TX_BUFSIZE
#define CFG_TUD_CDC_TX_BUFSIZE 1024
#endif

#ifndef CFG_TUD_CDC_EP_BUFSIZE
#define CFG_TUD_CDC_EP_BUFSIZE 64
#endif

/* HID endpoint buffer: enough for keyboard and absolute mouse reports. */
#ifndef CFG_TUD_HID_EP_BUFSIZE
#define CFG_TUD_HID_EP_BUFSIZE 64
#endif

#ifdef __cplusplus
}
#endif

#endif /* GT_SUPER_CONTROLLER_TUSB_CONFIG_H */
