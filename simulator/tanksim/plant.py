"""A plant model that produces a plausible value for every Phase 1 signal.

The model is driven entirely by the signal list: which signals exist, their
units, valid ranges, classes and wiring all come from
``interfaces/signals-v1.yaml``. Nothing dispatches on a numeric id, a channel
number or a debounce figure, so adding a signal to the list makes the simulator
produce it without a code change, and a signal the model has no generator for
is reported as ``unconfigured`` rather than invented.

Phase 1 scope: this produces *readings*, including the status of the hardwired
safety-chain and alarm contacts, which the controller only ever reads. It
produces no command, no setpoint and no output of any kind. There is no
over-temperature trip, emergency stop, fire, gas, ambient or wind input,
because those are not wired to this board (AGENTS.md section 5).

The waveforms are deliberately simple and periodic: the simulator exists so the
other components can be exercised, not to model asphalt thermodynamics. ADR-0003
and ADR-0008 both need repeatable inputs more than they need realism.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .signals import Signal, SignalList

#: What the model could determine about one signal this scan.
SampleStatus = Literal["ok", "fault", "unconfigured"]

# Names of the device-health signals the model knows how to produce. These are
# names, not ids: `name` is the identifier that appears in code and in the API
# (interfaces/README.md), while an id is data. A health signal the list gains
# later is reported as unconfigured until a generator is written for it.
HEALTH_UPTIME = "health_uptime"
HEALTH_LOG_BUFFER_USED = "health_log_buffer_used"
HEALTH_CLOUD_LINK_UP = "health_cloud_link_up"


@dataclass(frozen=True)
class Sample:
    """One raw observation, before the record's quality flag is decided."""

    value: float | bool | None
    status: SampleStatus = "ok"


@dataclass(frozen=True)
class PlantState:
    """The device state the health signals report on."""

    uptime_ms: int
    uptime_s: int
    link_up: bool
    buffer_fraction: float


@dataclass(frozen=True)
class PlantConfig:
    """Configuration of the waveforms. Defaults, not magic numbers.

    ``[Confirm]`` The periods and spreads below are chosen to make a short run
    show movement on every signal. They are not plant measurements; once the
    client supplies real fill and heating rates these become the place to put
    them.
    """

    #: Seconds for one full sweep of an analogue input across its range.
    analogue_period_s: float = 600.0
    #: Fraction of the valid range the analogue sweep uses, centred in it, so a
    #: healthy run never sits on the range limit.
    analogue_span_fraction: float = 0.8
    #: Seconds for one full product-temperature cycle.
    temperature_period_s: float = 1800.0
    #: Fraction of the valid range the temperature cycle uses.
    temperature_span_fraction: float = 0.5
    #: Degrees Celsius between the bottom and the upper level of the tank, the
    #: bottom being hotter because the base heater is there.
    temperature_level_spread_degc: float = 6.0
    #: Degrees Celsius between the two sensors of a pair, 180 degrees apart.
    temperature_orientation_spread_degc: float = 1.5
    #: Seconds for one on-off cycle of an equipment-status channel.
    equipment_period_s: float = 300.0
    #: Fraction of that cycle an equipment channel reads as running.
    equipment_duty: float = 0.5

    def __post_init__(self) -> None:
        for name in ("analogue_period_s", "temperature_period_s", "equipment_period_s"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("analogue_span_fraction", "temperature_span_fraction", "equipment_duty"):
            if not 0.0 < getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be above 0 and at most 1")


# Level names in the signal list, bottom first, used to place a PT100 in the
# temperature profile. The order matters, not the strings' meaning to Python.
_LEVEL_ORDER = ("bottom", "middle", "upper")


def _sine_within(low: float, high: float, span_fraction: float, phase: float) -> float:
    """A sine sweep centred in ``low..high`` using ``span_fraction`` of it."""
    centre = (low + high) / 2.0
    amplitude = (high - low) / 2.0 * span_fraction
    return centre + amplitude * math.sin(phase)


class PlantModel:
    """Produces one :class:`Sample` per signal per scan."""

    def __init__(self, signal_list: SignalList, config: PlantConfig | None = None) -> None:
        self._signals = signal_list
        self._config = config or PlantConfig()

    @property
    def config(self) -> PlantConfig:
        """The waveform configuration in use."""
        return self._config

    def sample(self, signal: Signal, state: PlantState) -> Sample:
        """Observe ``signal`` in the given device state."""
        generator = {
            "analogue": self._sample_analogue,
            "temperature": self._sample_temperature,
            "digital": self._sample_digital,
            "health": self._sample_health,
        }.get(signal.group)
        if generator is None:
            return Sample(value=None, status="unconfigured")
        return generator(signal, state)

    def sample_all(self, state: PlantState) -> dict[int, Sample]:
        """Observe every signal in the list, keyed by id."""
        return {signal.id: self.sample(signal, state) for signal in self._signals}

    # -- per-group generators ---------------------------------------------

    def _sample_analogue(self, signal: Signal, state: PlantState) -> Sample:
        low, high = self._require_range(signal)
        phase = 2 * math.pi * (state.uptime_ms / 1000.0) / self._config.analogue_period_s
        # The two loops are offset so the radar and pressure level readings are
        # not identical; comparing them is Phase 2, but they should not look
        # like one sensor read twice.
        phase += self._channel_phase(signal)
        return Sample(value=_sine_within(low, high, self._config.analogue_span_fraction, phase))

    def _sample_temperature(self, signal: Signal, state: PlantState) -> Sample:
        low, high = self._require_range(signal)
        phase = 2 * math.pi * (state.uptime_ms / 1000.0) / self._config.temperature_period_s
        base = _sine_within(low, high, self._config.temperature_span_fraction, phase)

        level = str(signal.source.get("level", ""))
        if level in _LEVEL_ORDER:
            # Bottom hottest: the base heater sits there. The spread is split
            # evenly across however many levels the list defines.
            steps = len(_LEVEL_ORDER) - 1
            position = _LEVEL_ORDER.index(level)
            base -= self._config.temperature_level_spread_degc * position / steps

        # The two sensors of a pair sit 180 degrees apart; the far side runs
        # slightly cooler. Comparing the pair is a Phase 2 check.
        if float(signal.source.get("orientation_deg", 0)) != 0.0:
            base -= self._config.temperature_orientation_spread_degc

        return Sample(value=base)

    def _sample_digital(self, signal: Signal, state: PlantState) -> Sample:
        if signal.safety_path:
            # Safety-chain and alarm contacts read healthy in a normal run. The
            # alarm states are produced by injecting a fault, which is how a
            # consumer should be tested: see tanksim.faults.
            return Sample(value=False)
        period = self._config.equipment_period_s
        position = ((state.uptime_ms / 1000.0) / period + self._duty_phase(signal)) % 1.0
        return Sample(value=position < self._config.equipment_duty)

    def _sample_health(self, signal: Signal, state: PlantState) -> Sample:
        if signal.name == HEALTH_UPTIME:
            return Sample(value=float(state.uptime_s))
        if signal.name == HEALTH_LOG_BUFFER_USED:
            low, high = signal.valid_range or (0.0, 100.0)
            return Sample(value=low + (high - low) * state.buffer_fraction)
        if signal.name == HEALTH_CLOUD_LINK_UP:
            return Sample(value=state.link_up)
        # A health signal the list gained after this model was written.
        return Sample(value=None, status="unconfigured")

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _require_range(signal: Signal) -> tuple[float, float]:
        if signal.valid_range is None:
            raise ValueError(
                f"signal {signal.id} ({signal.name}) has no valid_range, so the model "
                "cannot place a value inside it"
            )
        return signal.valid_range

    @staticmethod
    def _channel_phase(signal: Signal) -> float:
        """A per-channel phase offset, so sibling channels differ."""
        channel = int(signal.source.get("channel", signal.source.get("chip_select", 0)))
        return channel * math.pi / 4.0

    @staticmethod
    def _duty_phase(signal: Signal) -> float:
        """A per-channel offset into the on-off cycle, as a fraction of it."""
        channel = int(signal.source.get("channel", 0))
        return (channel % 10) / 10.0
