#include "boot_time.h"

#include <errno.h>
#include <string.h>

static bool initialised(const struct tank_boot_time *bt)
{
	return bt != NULL && bt->config.agreement_limit_ms != 0U;
}

int tank_boot_time_init(struct tank_boot_time *bt, const uint8_t boot_id[TANK_BOOT_ID_LEN],
			const struct tank_boot_time_config *config)
{
	if (bt == NULL || boot_id == NULL || config == NULL || config->agreement_limit_ms == 0U) {
		return -EINVAL;
	}

	memset(bt, 0, sizeof(*bt));
	bt->config = *config;
	memcpy(bt->boot_id, boot_id, TANK_BOOT_ID_LEN);
	bt->time_known = false;
	bt->warning_active = false;
	return 0;
}

int tank_boot_time_record_sync(struct tank_boot_time *bt, uint32_t up_ms, uint64_t epoch_ms)
{
	int64_t candidate_offset_ms;
	int64_t drift_ms;

	if (!initialised(bt)) {
		return -EINVAL;
	}

	candidate_offset_ms = (int64_t)epoch_ms - (int64_t)up_ms;

	if (bt->time_known) {
		drift_ms = candidate_offset_ms - bt->epoch_offset_ms;
		if (drift_ms < 0) {
			drift_ms = -drift_ms;
		}
		bt->warning_active = (uint64_t)drift_ms > bt->config.agreement_limit_ms;
	} else {
		/* First sync defines the estimate; there is nothing yet to
		 * disagree with, so this can never itself raise the warning.
		 */
		bt->warning_active = false;
	}

	bt->epoch_offset_ms = candidate_offset_ms;
	bt->time_known = true;
	return 0;
}

int tank_boot_time_record_sync_failure(struct tank_boot_time *bt)
{
	if (!initialised(bt)) {
		return -EINVAL;
	}

	/* Deliberately a no-op on time_known and warning_active: see the
	 * header comment. A failed retry changes nothing about what the
	 * device already knew or had already flagged.
	 */
	return 0;
}

int tank_boot_time_stamp(const struct tank_boot_time *bt, uint32_t up_ms,
			 struct tank_boot_time_stamp *out)
{
	if (!initialised(bt) || out == NULL) {
		return -EINVAL;
	}

	memcpy(out->boot_id, bt->boot_id, TANK_BOOT_ID_LEN);
	out->up_ms = up_ms;
	out->tk = bt->time_known;

	if (bt->time_known) {
		int64_t epoch_ms = (int64_t)up_ms + bt->epoch_offset_ms;

		out->t_s = (uint64_t)(epoch_ms / 1000);
	} else {
		out->t_s = 0U;
	}

	return 0;
}

bool tank_boot_time_warning_active(const struct tank_boot_time *bt)
{
	return bt != NULL && bt->warning_active;
}

bool tank_boot_time_known(const struct tank_boot_time *bt)
{
	return bt != NULL && bt->time_known;
}
