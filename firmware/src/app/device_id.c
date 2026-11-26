/*
 * The device ID every record carries (S-061). See device_id.h.
 */

#include "device_id.h"

#include <errno.h>

#include <zephyr/drivers/hwinfo.h>

static const char hex_digits[] = "0123456789abcdef";

int tank_device_id_format(const uint8_t *uid, size_t uid_len, char *out, size_t cap)
{
	if ((uid == NULL) || (out == NULL) || (uid_len == 0U) ||
	    (uid_len > TANK_DEVICE_ID_UID_MAX) || (cap < 2U * uid_len + 1U)) {
		return -EINVAL;
	}
	for (size_t i = 0U; i < uid_len; i++) {
		out[2U * i] = hex_digits[uid[i] >> 4];
		out[2U * i + 1U] = hex_digits[uid[i] & 0x0FU];
	}
	out[2U * uid_len] = '\0';
	return 0;
}

int tank_device_id_read(char *out, size_t cap)
{
	/* One byte spare, so an ID longer than the limit shows and is refused. */
	uint8_t uid[TANK_DEVICE_ID_UID_MAX + 1U];
	ssize_t n = hwinfo_get_device_id(uid, sizeof(uid));

	if (n < 0) {
		return (int)n;
	}
	return tank_device_id_format(uid, (size_t)n, out, cap);
}
