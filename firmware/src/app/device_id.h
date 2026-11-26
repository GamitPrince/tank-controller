/*
 * The device ID every record carries (S-061, ADR-0005).
 *
 * It is the MCU's factory unique ID, read with Zephyr's hwinfo API, written as
 * lowercase hex (tech lead, 26 Nov 2026). It is fixed in silicon, so nothing
 * has to be provisioned or can be lost; the provisioning bench step reads it
 * off the device and prints it on the QR label (ADR-0005 decision 2). The
 * MCX N's 16-byte ID gives 32 characters, the record encoder's limit
 * (TANK_RECORD_DEV_ID_MAX), which is why there is no prefix.
 */

#ifndef TANK_APP_DEVICE_ID_H_
#define TANK_APP_DEVICE_ID_H_

#include <stddef.h>
#include <stdint.h>

/* The longest factory ID used; a longer one is refused, not cut short. */
#define TANK_DEVICE_ID_UID_MAX 16U
/* Room for the hex form of the longest ID and its NUL. */
#define TANK_DEVICE_ID_BUF_LEN (2U * TANK_DEVICE_ID_UID_MAX + 1U)

/*
 * Write uid as lowercase hex into out. Returns 0, or -EINVAL if uid or out is
 * NULL, uid_len is 0 or above TANK_DEVICE_ID_UID_MAX, or cap is too small.
 */
int tank_device_id_format(const uint8_t *uid, size_t uid_len, char *out, size_t cap);

/*
 * Read this MCU's factory ID and format it into out. Returns 0, -EINVAL as
 * above, or the hwinfo error (-ENOSYS where the SoC has no unique ID).
 */
int tank_device_id_read(char *out, size_t cap);

#endif /* TANK_APP_DEVICE_ID_H_ */
