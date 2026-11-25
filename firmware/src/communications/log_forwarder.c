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

static int ack_delivered(const struct tank_log_forwarder *fw, size_t count, int sent)
{
	int rc;

	if (sent < 0) {
		tank_flash_log_rewind(fw->log);
		return sent;
	}
	if (sent == 0 || (size_t)sent > count) {
		tank_flash_log_rewind(fw->log);
		return -EINVAL;
	}
	rc = tank_flash_log_ack(fw->log, fw->batch[sent - 1].end_pos);
	if ((size_t)sent < count) {
		/* Read again from the first item that was not acknowledged. */
		tank_flash_log_rewind(fw->log);
	}
	return (rc != 0) ? rc : sent;
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
	if (rc != 0) {
		tank_flash_log_rewind(fw->log);
		return rc;
	}
	if (count == 0U) {
		return 0;
	}
	return ack_delivered(fw, count, fw->send_fn(fw->ctx, fw->batch, count));
}
