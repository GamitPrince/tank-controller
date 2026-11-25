/*
 * Forward the flash log to the cloud, oldest first (S-039, P1-14).
 */

#include "log_forwarder.h"

#include <errno.h>

static int fill_batch(const struct tank_log_forwarder *fw, size_t *count)
{
	*count = 0U;
	while (*count < fw->batch_cap) {
		int rc = tank_flash_log_read_next(fw->log, &fw->batch[*count]);

		if (rc == -ENODATA) {
			break;
		}
		if (rc != 0) {
			return rc;
		}
		(*count)++;
	}
	return 0;
}

int tank_log_forwarder_poll(const struct tank_log_forwarder *fw)
{
	size_t count;
	int rc;

	if (fw == NULL || fw->log == NULL || fw->send_fn == NULL || fw->batch == NULL ||
	    fw->batch_cap == 0U) {
		return -EINVAL;
	}
	rc = fill_batch(fw, &count);
	if (rc == 0 && count > 0U) {
		rc = fw->send_fn(fw->ctx, fw->batch, count);
	}
	if (count == 0U && rc == 0) {
		return 0;
	}
	if (rc != 0) {
		tank_flash_log_rewind(fw->log);
		return rc;
	}
	rc = tank_flash_log_ack(fw->log, fw->batch[count - 1U].end_pos);
	return (rc != 0) ? rc : (int)count;
}
