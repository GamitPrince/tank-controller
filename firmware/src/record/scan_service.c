/*
 * Take a scan every second and log it (S-059, P1-12, P1-14).
 * See scan_service.h for the behaviour.
 */

#include "scan_service.h"

#include <errno.h>

/* Room for the builder and the flash log's append; the scan itself lives in
 * the service struct, not on this stack.
 */
#define SERVICE_STACK_SIZE 4096
/* Above the uplink service (S-049): taking scans never waits for forwarding. */
#define SERVICE_PRIORITY K_PRIO_PREEMPT(5)

K_THREAD_STACK_DEFINE(scan_service_stack, SERVICE_STACK_SIZE);

static atomic_t service_running = ATOMIC_INIT(0);

int64_t tank_scan_service_next_deadline(int64_t deadline_ms, int64_t now_ms, uint32_t period_ms,
					uint32_t *skipped)
{
	int64_t next = deadline_ms + period_ms;
	uint32_t missed = 0U;

	if (next <= now_ms) {
		missed = (uint32_t)((now_ms - next) / period_ms) + 1U;
		next += (int64_t)missed * period_ms;
	}
	*skipped = missed;
	return next;
}

static void take_scan(struct tank_scan_service *svc, uint32_t now_ms)
{
	int err;

	if (svc->in.lock != NULL) {
		(void)k_mutex_lock(svc->in.lock, K_FOREVER);
	}
	err =
	    tank_scan_build(svc->in.sources, svc->in.bt, svc->cfg.sl, svc->seq, now_ms, &svc->scan);
	if (svc->in.lock != NULL) {
		(void)k_mutex_unlock(svc->in.lock);
	}
	if (err != 0) {
		svc->stats.build_errors++;
		svc->stats.last_error = err;
		return;
	}
	svc->seq++;
	err = tank_flash_log_append(svc->in.log, &svc->scan);
	if (err != 0) {
		svc->stats.append_errors++;
		svc->stats.last_error = err;
		return;
	}
	svc->stats.scans++;
}

static void service_main(void *p1, void *p2, void *p3)
{
	struct tank_scan_service *svc = p1;
	int64_t deadline = k_uptime_get();

	ARG_UNUSED(p2);
	ARG_UNUSED(p3);
	while (!atomic_get(&svc->stopping)) {
		uint32_t skipped;
		int64_t wait = deadline - k_uptime_get();

		if (wait > 0) {
			(void)k_sem_take(&svc->wake, K_MSEC(wait));
			continue;
		}
		take_scan(svc, k_uptime_get_32());
		deadline = tank_scan_service_next_deadline(deadline, k_uptime_get(),
							   svc->cfg.period_ms, &skipped);
		svc->stats.skipped += skipped;
	}
}

static bool inputs_valid(const struct tank_scan_service_inputs *in)
{
	return (in->sources != NULL) && (in->bt != NULL) && (in->log != NULL);
}

int tank_scan_service_start(struct tank_scan_service *svc,
			    const struct tank_scan_service_inputs *in,
			    const struct tank_scan_service_config *cfg)
{
	if ((svc == NULL) || (in == NULL) || (cfg == NULL) || !inputs_valid(in) ||
	    (cfg->period_ms == 0U)) {
		return -EINVAL;
	}
	if (!atomic_cas(&service_running, 0, 1)) {
		return -EALREADY;
	}
	*svc = (struct tank_scan_service){.in = *in, .cfg = *cfg, .seq = 1U};
	k_sem_init(&svc->wake, 0, 1);
	svc->tid = k_thread_create(&svc->thread, scan_service_stack,
				   K_THREAD_STACK_SIZEOF(scan_service_stack), service_main, svc,
				   NULL, NULL, SERVICE_PRIORITY, 0, K_NO_WAIT);
	return 0;
}

int tank_scan_service_stop(struct tank_scan_service *svc)
{
	if ((svc == NULL) || (svc->tid == NULL)) {
		return -EINVAL;
	}
	atomic_set(&svc->stopping, 1);
	k_sem_give(&svc->wake);
	(void)k_thread_join(&svc->thread, K_FOREVER);
	svc->tid = NULL;
	atomic_set(&service_running, 0);
	return 0;
}

const struct tank_scan_service_stats *tank_scan_service_stats(const struct tank_scan_service *svc)
{
	return (svc == NULL) ? NULL : &svc->stats;
}
