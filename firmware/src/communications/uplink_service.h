/*
 * Run the log forwarder in its own thread (S-049, P1-12).
 *
 * One thread polls tank_log_forwarder_poll() (S-039) for as long as the
 * service runs. When a poll delivered a full batch it polls again at once, so
 * a backlog after an outage drains batch after batch; when it delivered less
 * (S-063) or nothing, the log is caught up and it waits idle_ms, which lets
 * the next batch fill; when the link acknowledged nothing it waits retry_ms. The thread
 * has its own stack because one send can block for seconds (S-045: the
 * link's ack timeout times its attempts, per record), which must not stall
 * the system work queue.
 *
 * Transmit only: the service forwards what the flash log already holds and
 * acts on nothing it receives.
 *
 * There is one service thread, so at most one service runs at a time.
 */

#ifndef TANK_COMMUNICATIONS_UPLINK_SERVICE_H_
#define TANK_COMMUNICATIONS_UPLINK_SERVICE_H_

#include <stdbool.h>
#include <stdint.h>

#include <zephyr/kernel.h>

#include "log_forwarder.h"

struct tank_uplink_service_config {
	/* Wait after a poll that found nothing to send. */
	uint32_t idle_ms;
	/* Wait after a poll that failed. */
	uint32_t retry_ms;
	/*
	 * A poll that delivered at least this many polls again at once; fewer
	 * means caught up. 0 polls again after any delivery (S-049).
	 */
	uint32_t full_batch;
};

struct tank_uplink_service_stats {
	uint32_t polls;
	uint32_t delivered;
	uint32_t errors;
	int last_error;
};

/* Treat the fields as private; read the counters through stats. */
struct tank_uplink_service {
	const struct tank_log_forwarder *fw;
	struct tank_uplink_service_config cfg;
	struct k_thread thread;
	k_tid_t tid;
	atomic_t stopping;
	/* Given by stop or kick, so a sleeping thread wakes at once. */
	struct k_sem wake;
	struct tank_uplink_service_stats stats;
};

/*
 * How long to wait after a poll that returned result: 0 after a full batch
 * (any delivery when full_batch is 0), idle_ms when caught up, retry_ms after
 * an error.
 */
uint32_t tank_uplink_service_next_delay(int result, const struct tank_uplink_service_config *cfg);

/*
 * Start the service thread for fw. fw and the log behind it must already be
 * set up and stay valid while the service runs. Returns 0, -EINVAL, or
 * -EALREADY when a service is already running.
 */
int tank_uplink_service_start(struct tank_uplink_service *svc, const struct tank_log_forwarder *fw,
			      const struct tank_uplink_service_config *cfg);

/*
 * Stop the thread after its current poll and wait for it to end. Returns 0,
 * or -EINVAL when svc is not running.
 */
int tank_uplink_service_stop(struct tank_uplink_service *svc);

/*
 * Poll at once instead of finishing the current wait (S-065): the scan
 * service calls this when a scan with a prompt change was logged. A kick
 * during a poll makes the next poll start straight after it. Returns 0, or
 * -EINVAL when svc is not running.
 */
int tank_uplink_service_kick(struct tank_uplink_service *svc);

/* The service's counters, or NULL when svc is NULL. */
const struct tank_uplink_service_stats *
tank_uplink_service_stats(const struct tank_uplink_service *svc);

#endif /* TANK_COMMUNICATIONS_UPLINK_SERVICE_H_ */
