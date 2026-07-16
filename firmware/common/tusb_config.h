#ifndef GT_SUPER_CONTROLLER_TUSB_CONFIG_H
#define GT_SUPER_CONTROLLER_TUSB_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

#include "tusb_option.h"

/* Raspberry Pi Pico / RP2040 */
#ifndef CFG_TUSB_MCU
#define CFG_TUSB_MCU OPT_MCU_RP2040
#endif

/*
 * Pico SDK bazı derleme ayarlarında CFG_TUSB_OS değerini
 * komut satırından tanımlayabilir. Tekrar tanımlama hatasını
 * engellemek için yalnızca tanımlı değilse oluşturuyoruz.
 */
#ifndef CFG_TUSB_OS
#define CFG_TUSB_OS OPT_OS_NONE
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

/* USB Device */
#ifndef CFG_TUD_ENABLED
#define CFG_TUD_ENABLED 1
#endif

#ifndef CFG_TUD_ENDPOINT0_SIZE
#define CFG_TUD_ENDPOINT0_SIZE 64
#endif

/* Kullanılmayan USB sınıfları */
#ifndef CFG_TUD_CDC
#define CFG_TUD_CDC 1
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

/* HID: Klavye veya silah mouse cihazları */
#ifndef CFG_TUD_HID
#define CFG_TUD_HID 1
#endif

/* CDC seri haberleşme tamponları */
#ifndef CFG_TUD_CDC_RX_BUFSIZE
#define CFG_TUD_CDC_RX_BUFSIZE 256
#endif

#ifndef CFG_TUD_CDC_TX_BUFSIZE
#define CFG_TUD_CDC_TX_BUFSIZE 256
#endif

#ifndef CFG_TUD_CDC_EP_BUFSIZE
#define CFG_TUD_CDC_EP_BUFSIZE 64
#endif

/* HID tampon boyutu */
#ifndef CFG_TUD_HID_EP_BUFSIZE
#define CFG_TUD_HID_EP_BUFSIZE 64
#endif

#ifdef __cplusplus
}
#endif

#endif /* GT_SUPER_CONTROLLER_TUSB_CONFIG_H */
