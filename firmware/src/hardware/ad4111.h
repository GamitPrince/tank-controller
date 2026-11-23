/*
 * AD4111 24-bit ADC: data register and status byte decode for the 4-20 mA
 * current inputs.
 *
 * Story S-034 (P1-04). ADR-0002: radar level on AD4111 channel 1 and pressure
 * level on channel 2, input-only. ADR-0003: own small hardware-layer module,
 * no SPI binding here, the same split as max31865.h.
 *
 * This module only turns the chip's own bytes into a loop current and the
 * status flags the chip reports. It does not read SPI or devicetree and does
 * not know what a channel measures. Deciding whether a current is a healthy
 * 4-20 mA signal, below range, above range or an open circuit is the
 * measurement layer's job.
 *
 * Frame: the 24-bit data register, most significant byte first, followed by
 * the status byte the chip appends when its DATA_STAT option is on (bit 7
 * RDY, active low; bit 6 ADC_ERROR; bit 5 CRC_ERROR; bit 4 REG_ERROR; bits
 * 3:0 the channel the conversion belongs to). Unipolar coding is assumed:
 * code 0 is 0 mA and code 2^24 is the full-scale current.
 *
 * [Confirm] Full-scale current of the AD4111 current input and its coding
 * (datasheet check with the EE). It is a parameter here, not a constant, so
 * the figure lives in one place in the caller.
 */

#ifndef TANK_HARDWARE_AD4111_H_
#define TANK_HARDWARE_AD4111_H_

#include <stdbool.h>
#include <stdint.h>

/* Channels used in Phase 1 (ADR-0002: two of the four current inputs). */
#define TANK_AD4111_CHANNEL_MIN 1U
#define TANK_AD4111_CHANNEL_MAX 2U

/* Status byte bits as the chip defines them. */
enum tank_ad4111_status_bit {
	TANK_AD4111_STATUS_NOT_READY = 1U << 7,
	TANK_AD4111_STATUS_ADC_ERROR = 1U << 6,
	TANK_AD4111_STATUS_CRC_ERROR = 1U << 5,
	TANK_AD4111_STATUS_REG_ERROR = 1U << 4,
};

/* Mask of the channel number in the status byte. */
#define TANK_AD4111_STATUS_CHANNEL_MASK 0x0FU

struct tank_ad4111_reading {
	/* Loop current in mA, meaningful only when tank_ad4111_reading_ok() is true. */
	float current_ma;
	/* The 24-bit ADC code the current was computed from. */
	uint32_t raw_code24;
	/* Channel number reported by the chip in the status byte. */
	uint8_t channel;
	/* True when RDY was high: no fresh conversion, the data register is old. */
	bool not_ready;
	bool adc_error;
	bool crc_error;
	bool reg_error;
};

/*
 * Decode one conversion. data holds the three data-register bytes, most
 * significant first; status is the appended status byte; full_scale_ma is the
 * current at code 2^24 and must be positive.
 *
 * Returns 0 on success, or -EINVAL if data or out is NULL or full_scale_ma is
 * not positive. On failure out is left untouched.
 */
int tank_ad4111_decode(const uint8_t data[3], uint8_t status, float full_scale_ma,
		       struct tank_ad4111_reading *out);

/* True when the chip reported a fresh conversion with no error flag set. */
bool tank_ad4111_reading_ok(const struct tank_ad4111_reading *reading);

#endif /* TANK_HARDWARE_AD4111_H_ */
