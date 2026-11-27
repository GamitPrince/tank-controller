"""Drift guard: the decoder's constants against ``interfaces/records.cddl`` (S-067).

The decoder checks fields itself rather than interpreting the schema file, so
these tests read the file and fail if the version or the quality codes change
there without changing here. The ``backend`` CI job runs on every change under
``interfaces/``, so a schema change cannot pass CI without them.
"""

import re
from pathlib import Path

from tankapi.records import MAX_BATCH_RECORDS, RECORD_SCHEMA_VERSION, Quality

SCHEMA = (Path(__file__).parents[2] / "interfaces" / "records.cddl").read_text()


def test_quality_codes_match_the_schema() -> None:
    group = re.search(r"^quality-values = \((.*?)^\)", SCHEMA, re.MULTILINE | re.DOTALL)
    assert group is not None
    codes = dict(re.findall(r"^\s*([a-z-]+): (\d+),", group.group(1), re.MULTILINE))

    assert {name.replace("-", "_").upper(): int(code) for name, code in codes.items()} == {
        quality.name: quality.value for quality in Quality
    }


def test_record_version_and_batch_size_match_the_schema() -> None:
    assert set(re.findall(r"^\s*v: (\d+),", SCHEMA, re.MULTILINE)) == {str(RECORD_SCHEMA_VERSION)}
    assert re.search(rf"^batch = \[1\*{MAX_BATCH_RECORDS} message\]$", SCHEMA, re.MULTILINE)
