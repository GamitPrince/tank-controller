/*
 * Run the log forwarder in its own thread (S-049, P1-12).
 * See uplink_service.h for the behaviour.
 */

#include "uplink_service.h"

#include <errno.h>

/* Room for the forwarder, the uplink's CBOR encoder and the link sender. */
#define SERVICE_STACK_SIZE 4096
/* Below the scan thread's priority-to-be: forwarding can always wait. */
#define SERVICE_PRIORITY K_PRIO_PREEMPT(10)

K_THREAD_STACK_DEFINE(service_stack, SERVICE_STACK_SIZE);

static atomic_t service_running = ATOMIC_INIT(0);

uint32_t tank_uplink_service_next_delay(int result, const struct tank_uplink_service_config *cfg)
{
	if (result > 0) {
		return 0U;
	}
	return (result == 0) ? cfg->idle_ms : cfg->retry_ms;
}

static void count(struct tank_uplink_service *svc, int result)
{
	svc->stats.polls++;
	if (result > 0) {
		svc->stats.delivered += (uint32_t)result;
	} else if (result < 0) {
		svc->stats.errors++;
		svc->stats.last_error = result;
	}
}

static void service_main(void *p1, void *p2, void *p3)
{
	struct tank_uplink_service *svc = p1;

	ARG_UNUSED(p2);
	ARG_UNUSED(p3);
	while (!atomic_get(&svc->stopping)) {
		int result = tank_log_forwarder_poll(svc->fw);
		uint32_t delay = tank_uplink_service_next_delay(result, &svc->cfg);

		count(svc, result);
		if (delay > 0U) {
			(void)k_sem_take(&svc->wake, K_MSEC(delay));
		}
	}
}

int tank_uplink_service_start(struct tank_uplink_service *svc, const struct tank_log_forwarder *fw,
			      const struct tank_uplink_service_config *cfg)
{
	if (svc == NULL || fw == NULL || cfg == NULL) {
		return -EINVAL;
	}
	if (!atomic_cas(&service_running, 0, 1)) {
		return -EALREADY;
	}
	*svc = (struct tank_uplink_service){.fw = fw, .cfg = *cfg};
	k_sem_init(&svc->wake, 0, 1);
	svc->tid =
	    k_thread_create(&svc->thread, service_stack, K_THREAD_STACK_SIZEOF(service_stack),
			    service_main, svc, NULL, NULL, SERVICE_PRIORITY, 0, K_NO_WAIT);
	return 0;
}

int tank_uplink_service_stop(struct tank_uplink_service *svc)
{
	if (svc == NULL || svc->tid == NULL) {
		return -EINVAL;
	}
	atomic_set(&svc->stopping, 1);
	k_sem_give(&svc->wake);
	(void)k_thread_join(&svc->thread, K_FOREVER);
	svc->tid = NULL;
	atomic_set(&service_running, 0);
	return 0;
}

const struct tank_uplink_service_stats *
tank_uplink_service_stats(const struct tank_uplink_service *svc)
{
	return (svc == NULL) ? NULL : &svc->stats;
}
