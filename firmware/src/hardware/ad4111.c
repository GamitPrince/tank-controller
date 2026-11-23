/* AD4111 data and status decode. See ad4111.h. */

#include "ad4111.h"

#include <errno.h>
#include <stddef.h>

#define TANK_AD4111_ADC_CODE_BITS 24
#define TANK_AD4111_ADC_CODE_SCALE ((float)(1UL << TANK_AD4111_ADC_CODE_BITS))
#define TANK_AD4111_BYTE_BITS 8

int tank_ad4111_decode(const uint8_t data[3], uint8_t status, float full_scale_ma,
		       struct tank_ad4111_reading *out)
{
	if ((data == NULL) || (out == NULL) || !(full_scale_ma > 0.0f)) {
		return -EINVAL;
	}

	const uint32_t code = ((uint32_t)data[0] << (2 * TANK_AD4111_BYTE_BITS)) |
			      ((uint32_t)data[1] << TANK_AD4111_BYTE_BITS) | data[2];

	out->raw_code24 = code;
	out->current_ma = ((float)code / TANK_AD4111_ADC_CODE_SCALE) * full_scale_ma;
	out->channel = status & TANK_AD4111_STATUS_CHANNEL_MASK;
	out->not_ready = (status & TANK_AD4111_STATUS_NOT_READY) != 0U;
	out->adc_error = (status & TANK_AD4111_STATUS_ADC_ERROR) != 0U;
	out->crc_error = (status & TANK_AD4111_STATUS_CRC_ERROR) != 0U;
	out->reg_error = (status & TANK_AD4111_STATUS_REG_ERROR) != 0U;

	return 0;
}

bool tank_ad4111_reading_ok(const struct tank_ad4111_reading *reading)
{
	return (reading != NULL) && !reading->not_ready && !reading->adc_error &&
	       !reading->crc_error && !reading->reg_error;
}
