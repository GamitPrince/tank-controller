"""Tests for the schema-driven record validator.

These are the tests behind the acceptance criterion P1-03 deferred to this
story. They check two things: that a record the simulator produces passes the
schema in ``interfaces/``, and that the validator actually rejects records the
schema forbids — a validator that accepts everything would pass the first test
on its own.
"""

from __future__ import annotations

import pytest

from tanksim.cddl import Schema, SchemaError, UnsupportedConstruct, load_schema

GOOD_RECORD = {
    "v": 1,
    "dev": "SIM-0001",
    "sl": 1,
    "boot": bytes(range(16)),
    "seq": 0,
    "up": 1000,
    "tk": True,
    "t": 1763683200,
    "r": [{"id": 1001, "val": 12000, "q": 0, "age": 5}],
}


def without(key: str) -> dict:
    return {k: v for k, v in GOOD_RECORD.items() if k != key}


def replacing(**changes) -> dict:
    return {**GOOD_RECORD, **changes}


def test_the_real_schema_compiles(schema):
    assert "record" in schema.rule_names
    assert schema.source.endswith("records.cddl")


def test_a_well_formed_record_passes(schema):
    schema.validate(GOOD_RECORD)
    assert schema.matches(GOOD_RECORD)


def test_the_optional_unix_time_may_be_absent(schema):
    schema.validate(replacing(tk=False, **{}) | without("t"))


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (replacing(v=2), "literal 1"),
        (replacing(r=[]), "at least 1"),
        (replacing(boot=b"too short"), "size"),
        (replacing(dev=""), "outside 1..64"),
        (replacing(dev="x" * 65), "outside 1..64"),
        (replacing(dev=1234), "expected tstr"),
        (replacing(seq=-1), "expected uint"),
        (replacing(tk=1), "expected bool"),
        (replacing(extra=1), "unexpected member"),
        (without("up"), "required member 'up' is missing"),
        (replacing(r=[{"id": 1, "val": 1.5, "q": 0, "age": 1}]), "matches none"),
        (replacing(r=[{"id": 1, "val": 1, "q": 9, "age": 1}]), "not one of"),
        (replacing(r=[{"id": 1, "q": 0}]), "required member 'age' is missing"),
        (replacing(r={"id": 1}), "expected an array"),
        (replacing(r=[1]), "expected a map"),
    ],
)
def test_a_record_the_schema_forbids_is_rejected(schema, record, expected):
    with pytest.raises(SchemaError, match=expected):
        schema.validate(record)
    assert not schema.matches(record)


def test_a_bool_is_an_allowed_reading_value(schema):
    # A digital channel's value is a bool, which the schema allows alongside int.
    schema.validate(replacing(r=[{"id": 3001, "val": False, "q": 0, "age": 1}]))


def test_a_bool_is_not_an_integer(schema):
    # Python's bool is a subclass of int; CBOR and the schema keep them apart.
    with pytest.raises(SchemaError, match="expected uint"):
        schema.validate(replacing(seq=True))


def test_the_quality_codes_come_from_the_schema(schema):
    assert dict(schema.enum_values("quality-values")) == {
        "good": 0,
        "stale": 1,
        "out-of-range": 2,
        "fault": 3,
        "unconfigured": 4,
    }


def test_an_unknown_rule_is_reported(schema):
    with pytest.raises(SchemaError, match="no rule named"):
        schema.validate(GOOD_RECORD, rule="nope")


def test_a_group_rule_is_not_a_type(schema):
    with pytest.raises(UnsupportedConstruct, match="defines a group"):
        schema.validate(0, rule="quality-values")


def test_enum_values_on_a_rule_that_is_not_a_group(schema):
    with pytest.raises(UnsupportedConstruct, match="not a group"):
        schema.enum_values("record")


def test_the_default_schema_is_the_one_in_interfaces(interfaces_dir):
    assert load_schema().source == str(interfaces_dir / "records.cddl")


# -- the limits of this validator ---------------------------------------
#
# Unsupported CDDL must fail loudly at compile time. A construct silently
# ignored would make the validator claim more than it checks, which is the one
# thing this module must not do.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("start = {* tstr => int}", "wildcard map member"),
        ("start = {2* a: int}", "repeated or wildcard map member"),
        ('start = tstr .regexp "a+"', r"control operator \.regexp"),
        ("start = #6.37(bstr)", "unsupported CDDL construct Tag"),
        ("start = uint .size 4", "text or byte string"),
        ("start = (a: int // b: int)", "unsupported CDDL construct Group"),
    ],
)
def test_unsupported_cddl_is_refused_at_compile_time(text, expected):
    with pytest.raises(UnsupportedConstruct, match=expected):
        Schema(text)


def test_a_reference_to_a_missing_rule_is_refused_at_compile_time():
    with pytest.raises(SchemaError, match="no rule named 'nope'"):
        Schema("start = &nope\n")


def test_a_supported_subset_still_compiles():
    # Type choices, nested maps, arrays with bounded occurrence and exclusive
    # ranges are all inside the subset, so they must work.
    schema = Schema("start = {a: int / tstr, ? b: [1*2 inner]}\ninner = {c: bool}\nsmall = uint\n")
    schema.validate({"a": "text", "b": [{"c": True}]})
    schema.validate({"a": 3})
    with pytest.raises(SchemaError):
        schema.validate({"a": 3, "b": [{"c": True}, {"c": False}, {"c": True}]})


def test_a_trailing_element_is_rejected():
    schema = Schema("start = [1*1 uint]\n")
    with pytest.raises(SchemaError, match="trailing element"):
        schema.validate([1, 2])


def test_an_exclusive_range_excludes_its_top():
    schema = Schema("start = tstr .size (1...4)\n")
    schema.validate("abc")
    with pytest.raises(SchemaError, match=r"outside 1\.\.\.4"):
        schema.validate("abcd")


def test_a_literal_text_value_is_supported():
    schema = Schema('start = {kind: "scan"}\n')
    schema.validate({"kind": "scan"})
    with pytest.raises(SchemaError, match="literal"):
        schema.validate({"kind": "other"})
