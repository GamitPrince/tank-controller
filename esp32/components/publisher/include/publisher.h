/*
 * Publish the FRDM's batches to the cloud (S-064, P1-12; ADR-0004 amendment
 * 4, ADR-0006).
 *
 * Each new RECORD the link endpoint passes up (S-047) carries one batch of one
 * to five records (S-062, S-063). The publisher sends that payload unchanged,
 * at QoS 1, as one MQTT message on tank/{device_id}/records. Only when the
 * broker's PUBACK for that message arrives does it confirm the RECORD, and the
 * endpoint writes DELIVERED back to the FRDM. A publish that fails, or a
 * PUBACK that never comes, is never confirmed: the FRDM keeps the records in
 * its flash log and sends them again (ADR-0004 decision 3).
 *
 * The FRDM has one RECORD in flight at a time (S-043), so one publish waits
 * here at a time. A new RECORD while one waits means the FRDM gave up on the
 * old one; the old PUBACK, when it comes, confirms nothing.
 *
 * Phase 1: messages go to the cloud and only PUBACKs come back. Nothing here
 * subscribes to anything or commands the FRDM or the plant.
 *
 * Standard C only, so it is tested on a laptop with Unity (ADR-0006 decision
 * 3). The ESP-IDF MQTT client is reached through publish_fn, and its
 * published event is passed in through tank_publisher_on_puback().
 */

#ifndef TANK_ESP32_PUBLISHER_H_
#define TANK_ESP32_PUBLISHER_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "link_endpoint.h"

/* The record encoder's device ID limit (record_cbor.h, S-061). */
#define TANK_PUBLISHER_DEVICE_ID_MAX 32U
#define TANK_PUBLISHER_TOPIC_PREFIX "tank/"
#define TANK_PUBLISHER_TOPIC_SUFFIX "/records"
#define TANK_PUBLISHER_TOPIC_MAX                                                                   \
	(sizeof(TANK_PUBLISHER_TOPIC_PREFIX) - 1U + TANK_PUBLISHER_DEVICE_ID_MAX +                 \
	 sizeof(TANK_PUBLISHER_TOPIC_SUFFIX))

/*
 * Publish payload on topic at QoS 1. Returns the message id (above 0) the
 * PUBACK will carry, or a negative error (not connected, outbox full).
 */
typedef int (*tank_mqtt_publish_fn)(void *ctx, const char *topic, const uint8_t *payload,
				    size_t len);

struct tank_publisher_config {
	/* The DAQ's device ID, as provisioned with the ESP32's certificate. */
	const char *device_id;
	tank_mqtt_publish_fn publish_fn;
	void *mqtt_ctx;
	/* The link endpoint whose RECORDs this publishes and confirms. */
	struct tank_link_endpoint *endpoint;
};

struct tank_publisher_stats {
	uint32_t published;
	uint32_t confirmed;
	uint32_t publish_errors;
	/* PUBACKs for no message waiting here (the FRDM had given up). */
	uint32_t stale_acks;
	int last_error;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_publisher {
	struct tank_publisher_config cfg;
	char topic[TANK_PUBLISHER_TOPIC_MAX];
	bool waiting;
	int msg_id;
	uint16_t seq;
	struct tank_publisher_stats stats;
};

/*
 * Returns 0, or -EINVAL for a NULL argument or a device ID that is empty,
 * longer than TANK_PUBLISHER_DEVICE_ID_MAX, or holds a character MQTT treats
 * as special in a topic ('/', '+', '#').
 */
int tank_publisher_init(struct tank_publisher *pub, const struct tank_publisher_config *cfg);

/* The endpoint's record_fn; ctx is the struct tank_publisher. */
void tank_publisher_on_record(void *ctx, uint16_t seq, const uint8_t *payload, size_t len);

/*
 * The broker acknowledged message msg_id. Confirms the RECORD it carried.
 * Returns 0 (also for a stale PUBACK), -EINVAL for a NULL publisher, or the
 * endpoint's confirm error.
 */
int tank_publisher_on_puback(struct tank_publisher *pub, int msg_id);

/* The topic messages go to, or NULL when pub is NULL. */
const char *tank_publisher_topic(const struct tank_publisher *pub);

const struct tank_publisher_stats *tank_publisher_stats(const struct tank_publisher *pub);

#endif /* TANK_ESP32_PUBLISHER_H_ */
