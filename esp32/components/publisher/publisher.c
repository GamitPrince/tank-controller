/*
 * Publish the FRDM's batches to the cloud (S-064). See publisher.h.
 */

#include "publisher.h"

#include <errno.h>
#include <string.h>

static bool device_id_valid(const char *id)
{
	size_t n = 0U;

	if (id == NULL) {
		return false;
	}
	while ((n <= TANK_PUBLISHER_DEVICE_ID_MAX) && (id[n] != '\0')) {
		if ((id[n] == '/') || (id[n] == '+') || (id[n] == '#')) {
			return false;
		}
		n++;
	}
	return (n > 0U) && (n <= TANK_PUBLISHER_DEVICE_ID_MAX);
}

int tank_publisher_init(struct tank_publisher *pub, const struct tank_publisher_config *cfg)
{
	if ((pub == NULL) || (cfg == NULL) || (cfg->publish_fn == NULL) ||
	    (cfg->endpoint == NULL) || !device_id_valid(cfg->device_id)) {
		return -EINVAL;
	}
	const size_t prefix = sizeof(TANK_PUBLISHER_TOPIC_PREFIX) - 1U;
	const size_t id_len = strlen(cfg->device_id);

	memset(pub, 0, sizeof(*pub));
	pub->cfg = *cfg;
	memcpy(pub->topic, TANK_PUBLISHER_TOPIC_PREFIX, prefix);
	memcpy(&pub->topic[prefix], cfg->device_id, id_len);
	/* The suffix's sizeof includes its NUL, which ends the topic. */
	memcpy(&pub->topic[prefix + id_len], TANK_PUBLISHER_TOPIC_SUFFIX,
	       sizeof(TANK_PUBLISHER_TOPIC_SUFFIX));
	return 0;
}

void tank_publisher_on_record(void *ctx, uint16_t seq, const uint8_t *payload, size_t len)
{
	struct tank_publisher *pub = ctx;
	int msg_id;

	if ((pub == NULL) || (payload == NULL) || (len == 0U)) {
		return;
	}
	/* Whatever waited before is given up by the FRDM, so it is dropped. */
	pub->waiting = false;
	msg_id = pub->cfg.publish_fn(pub->cfg.mqtt_ctx, pub->topic, payload, len);
	if (msg_id <= 0) {
		pub->stats.publish_errors++;
		pub->stats.last_error = (msg_id < 0) ? msg_id : -EIO;
		return;
	}
	pub->waiting = true;
	pub->msg_id = msg_id;
	pub->seq = seq;
	pub->stats.published++;
}

int tank_publisher_on_puback(struct tank_publisher *pub, int msg_id)
{
	int err;

	if (pub == NULL) {
		return -EINVAL;
	}
	if (!pub->waiting || (msg_id != pub->msg_id)) {
		pub->stats.stale_acks++;
		return 0;
	}
	pub->waiting = false;
	err = tank_link_endpoint_confirm(pub->cfg.endpoint, pub->seq);
	if (err != 0) {
		pub->stats.last_error = err;
		return err;
	}
	pub->stats.confirmed++;
	return 0;
}

const char *tank_publisher_topic(const struct tank_publisher *pub)
{
	return (pub == NULL) ? NULL : pub->topic;
}

const struct tank_publisher_stats *tank_publisher_stats(const struct tank_publisher *pub)
{
	return (pub == NULL) ? NULL : &pub->stats;
}
