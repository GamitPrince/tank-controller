"""Shared fixtures.

The tests run against the real ``interfaces/`` contract, not a copy of it. That
is the point of the design: if the YAML or the CDDL changes in a way the
simulator does not follow, these tests fail, which is exactly the bug the
runtime loading exists to prevent.
"""

from __future__ import annotations

import pytest

from tanksim.cddl import Schema, load_schema
from tanksim.clock import SimClock
from tanksim.device import SimulatedDevice
from tanksim.faults import FaultPlan
from tanksim.interfaces import find_interfaces_dir
from tanksim.link import BufferedLink, RecordingSink
from tanksim.record import Quality
from tanksim.signals import SignalList, load_signal_list

# A fixed boot id and boot time, so a record is byte-for-byte reproducible.
TEST_BOOT_ID = bytes(range(16))
TEST_BOOT_UNIX_S = 1763683200
TEST_DEVICE_ID = "SIM-TEST-0001"


@pytest.fixture(scope="session")
def interfaces_dir():
    """The repository's ``interfaces/`` folder."""
    return find_interfaces_dir()


@pytest.fixture(scope="session")
def signal_list() -> SignalList:
    """The real Phase 1 signal list."""
    return load_signal_list()


@pytest.fixture(scope="session")
def schema() -> Schema:
    """The real compiled record schema."""
    return load_schema()


@pytest.fixture(scope="session")
def quality(schema: Schema) -> Quality:
    """The quality codes, as the schema defines them."""
    return Quality(schema)


@pytest.fixture(scope="session")
def device_id() -> str:
    """The device id the test device publishes under."""
    return TEST_DEVICE_ID


@pytest.fixture(scope="session")
def boot_id() -> bytes:
    """The fixed boot id, so a record is byte-for-byte reproducible."""
    return TEST_BOOT_ID


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def link(sink: RecordingSink) -> BufferedLink:
    return BufferedLink(sink)


@pytest.fixture
def make_device(signal_list: SignalList, schema: Schema):
    """Build a device with fixed identity, so records are reproducible."""

    def build(
        link: BufferedLink,
        fault_plan: FaultPlan | None = None,
        sntp_sync_after_ms: int = 0,
    ) -> SimulatedDevice:
        return SimulatedDevice(
            device_id=TEST_DEVICE_ID,
            signal_list=signal_list,
            link=link,
            clock=SimClock(boot_unix_s=TEST_BOOT_UNIX_S, sntp_sync_after_ms=sntp_sync_after_ms),
            fault_plan=fault_plan,
            schema=schema,
            boot_id=TEST_BOOT_ID,
        )

    return build
