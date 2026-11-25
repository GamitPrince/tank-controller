/* See sntp_client.h: not built or exercised by any test in this story. */

#include "sntp_client.h"

#include <errno.h>

#include <zephyr/net/sntp.h>

int tank_sntp_sync(const char *server, uint32_t timeout_ms, uint64_t *epoch_ms_out)
{
	struct sntp_time sntp_time;
	int rc;

	if (server == NULL || epoch_ms_out == NULL) {
		return -EINVAL;
	}

	rc = sntp_simple(server, timeout_ms, &sntp_time);
	if (rc != 0) {
		return rc;
	}

	/* sntp_time.seconds is Unix seconds; sntp_time.fraction is Q32.32
	 * fractional seconds, so the top 32 bits are whole-fraction counts
	 * out of 2^32.
	 */
	*epoch_ms_out = (uint64_t)sntp_time.seconds * 1000ULL +
			((uint64_t)(sntp_time.fraction >> 32) * 1000ULL) / 0x100000000ULL;
	return 0;
}
