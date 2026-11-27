/*
 * Boot the firmware application (S-060, P1-12, P1-14).
 * See tank_app.h for the behaviour.
 */

#include "tank_app.h"

#include <errno.h>

#include "alarm_input.h"
#include "equipment_status.h"
#include "link_sender.h"
#include "level_switch.h"
#include "loop_level.h"
#include "product_temperature.h"
#include "tank_level_signals.h" /* TANK_SIGNAL_LIST_VERSION, generated */

typedef size_t (*contact_count_fn)(void);
typedef const struct tank_level_switch_config *(*contact_at_fn)(size_t index);

static int init_levels(struct tank_app *app)
{
	const size_t n = tank_loop_level_config_count();

	if (n > TANK_APP_MAX_LEVELS) {
		return -ENOSPC;
	}
	for (size_t i = 0U; i < n; i++) {
		int err = tank_loop_level_init(&app->levels[i], tank_loop_level_config_at(i));

		if (err != 0) {
			return err;
		}
	}
	app->sources.levels = app->levels;
	app->sources.level_count = n;
	return 0;
}

static int init_temperatures(struct tank_app *app)
{
	const size_t n = tank_product_temperature_config_count();

	if (n > TANK_APP_MAX_TEMPERATURES) {
		return -ENOSPC;
	}
	for (size_t i = 0U; i < n; i++) {
		int err = tank_product_temperature_init(&app->temperatures[i],
							tank_product_temperature_config_at(i));

		if (err != 0) {
			return err;
		}
	}
	app->sources.temperatures = app->temperatures;
	app->sources.temperature_count = n;
	return 0;
}

/* Append one contact table after the contacts already set up. */
static int add_contacts(struct tank_app *app, contact_count_fn count, contact_at_fn at)
{
	const size_t n = count();

	if (app->sources.contact_count + n > TANK_APP_MAX_CONTACTS) {
		return -ENOSPC;
	}
	for (size_t i = 0U; i < n; i++) {
		int err = tank_level_switch_init(&app->contacts[app->sources.contact_count], at(i));

		if (err != 0) {
			return err;
		}
		app->sources.contact_count++;
	}
	return 0;
}

static int init_inputs(struct tank_app *app)
{
	int err = init_levels(app);

	if (err == 0) {
		err = init_temperatures(app);
	}
	app->sources.contacts = app->contacts;
	if (err == 0) {
		err =
		    add_contacts(app, tank_level_switch_config_count, tank_level_switch_config_at);
	}
	if (err == 0) {
		err = add_contacts(app, tank_alarm_input_config_count, tank_alarm_input_config_at);
	}
	if (err == 0) {
		err = add_contacts(app, tank_equipment_status_config_count,
				   tank_equipment_status_config_at);
	}
	return err;
}

/* The scan service's on_change: send a prompt change now (S-065, NFR-01). */
static void send_now(void *ctx)
{
	/* Before the uplink is up, or without one, there is nothing to wake. */
	(void)tank_uplink_service_kick(ctx);
}

static int start_scanning(struct tank_app *app, const struct tank_app_config *cfg)
{
	const struct tank_scan_service_inputs in = {.sources = &app->sources,
						    .bt = &app->bt,
						    .lock = &app->inputs_lock,
						    .log = &app->log,
						    .on_change =
							(cfg->esp32_uart != NULL) ? send_now : NULL,
						    .change_ctx = &app->forwarding};
	const struct tank_scan_service_config scan_cfg = {.period_ms = cfg->scan_period_ms,
							  .sl = TANK_SIGNAL_LIST_VERSION};

	k_mutex_init(&app->inputs_lock);
	return tank_scan_service_start(&app->scan, &in, &scan_cfg);
}

static int start_forwarding(struct tank_app *app, const struct tank_app_config *cfg)
{
	const struct tank_link_sender_config link_cfg = tank_link_sender_default_config();
	const struct tank_uplink_io io = {.write_fn = tank_esp32_uart_write,
					  .read_fn = tank_esp32_uart_read,
					  .now_fn = tank_esp32_uart_now,
					  .ctx = &app->uart};
	int err = tank_esp32_uart_init(&app->uart, cfg->esp32_uart);

	if (err == 0) {
		err = tank_uplink_init(&app->up, cfg->device_id, &link_cfg, &io);
	}
	if (err == 0) {
		app->fw = (struct tank_log_forwarder){.log = &app->log,
						      .send_fn = tank_uplink_send,
						      .ctx = &app->up,
						      .batch = app->batch,
						      .batch_cap = TANK_APP_UPLINK_BATCH};
		err = tank_uplink_service_start(&app->forwarding, &app->fw, &cfg->uplink);
	}
	return err;
}

int tank_app_start(struct tank_app *app, const struct tank_app_config *cfg)
{
	const struct tank_boot_time_config bt_cfg = {
	    .agreement_limit_ms = (cfg == NULL) ? 0U : cfg->clock_agreement_limit_ms};
	int err;

	if ((app == NULL) || (cfg == NULL) || (cfg->boot_id == NULL) ||
	    ((cfg->esp32_uart != NULL) && (cfg->device_id == NULL))) {
		return -EINVAL;
	}
	if (app->scan.tid != NULL) {
		/* Running: clearing it would pull the state from under its thread. */
		return -EALREADY;
	}
	*app = (struct tank_app){0};
	err = init_inputs(app);
	if (err == 0) {
		err = tank_boot_time_init(&app->bt, cfg->boot_id, &bt_cfg);
	}
	if (err == 0) {
		err = tank_flash_log_mount(&app->log, &cfg->log);
	}
	if (err == 0) {
		err = start_scanning(app, cfg);
	}
	if ((err == 0) && (cfg->esp32_uart != NULL)) {
		err = start_forwarding(app, cfg);
	}
	return err;
}

int tank_app_stop(struct tank_app *app)
{
	if (app == NULL) {
		return -EINVAL;
	}
	if (app->forwarding.tid != NULL) {
		(void)tank_uplink_service_stop(&app->forwarding);
	}
	return tank_scan_service_stop(&app->scan);
}

const struct tank_scan_sources *tank_app_sources(const struct tank_app *app)
{
	return (app == NULL) ? NULL : &app->sources;
}
