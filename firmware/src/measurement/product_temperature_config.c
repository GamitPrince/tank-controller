/*
 * The product temperature contracts, taken from the signal list at build time.
 *
 * tank_temperature_signals.h is generated from interfaces/signals-v1.yaml by
 * firmware/scripts/gen_temperature_signals.py and is never committed, so no
 * signal id, chip select, mounting position, update rate or valid range is
 * written into C. If a sensor is added to the signal list for this story, the
 * table below grows without any change here.
 *
 * The table is const: a caller can read a sensor's contract but cannot alter
 * what the contract says.
 */

#include "product_temperature.h"

#include <stddef.h>

#include "tank_temperature_signals.h"

/*
 * The parameter names are prefixed because macro substitution replaces a
 * parameter wherever its token appears, a field designator included: a
 * parameter called `level` would turn `.level = (level)` into
 * `.TANK_PRODUCT_LEVEL_UPPER = (TANK_PRODUCT_LEVEL_UPPER)`, which does not
 * compile.
 */
#define TANK_PRODUCT_TEMPERATURE_ENTRY(arg_name, arg_id, arg_chip_select, arg_level,               \
				       arg_orientation, arg_rate, arg_low, arg_high)               \
	{                                                                                          \
	    .signal_id = (arg_id),                                                                 \
	    .chip_select = (arg_chip_select),                                                      \
	    .level = (arg_level),                                                                  \
	    .orientation_deg = (arg_orientation),                                                  \
	    .update_rate_ms = (arg_rate),                                                          \
	    .valid_low_degc = (arg_low),                                                           \
	    .valid_high_degc = (arg_high),                                                         \
	},

static const struct tank_product_temperature_config sensors[] = {
    TANK_TEMPERATURE_SENSORS(TANK_PRODUCT_TEMPERATURE_ENTRY)};

#define SENSOR_COUNT (sizeof(sensors) / sizeof(sensors[0]))

/* The generator states the count as well, so a truncated table cannot build. */
_Static_assert(SENSOR_COUNT == TANK_TEMPERATURE_SENSOR_COUNT,
	       "the generated sensor table does not match its declared count");

size_t tank_product_temperature_config_count(void)
{
	return SENSOR_COUNT;
}

const struct tank_product_temperature_config *tank_product_temperature_config_at(size_t index)
{
	if (index >= SENSOR_COUNT) {
		return NULL;
	}

	return &sensors[index];
}

const struct tank_product_temperature_config *
tank_product_temperature_config_by_id(uint16_t signal_id)
{
	for (size_t i = 0; i < SENSOR_COUNT; i++) {
		if (sensors[i].signal_id == signal_id) {
			return &sensors[i];
		}
	}

	return NULL;
}

const struct tank_product_temperature_config *
tank_product_temperature_config_by_chip_select(uint8_t chip_select)
{
	for (size_t i = 0; i < SENSOR_COUNT; i++) {
		if (sensors[i].chip_select == chip_select) {
			return &sensors[i];
		}
	}

	return NULL;
}
