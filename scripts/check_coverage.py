#!/usr/bin/env python3
"""Fail if line coverage in a Cobertura XML report is below the minimum.

Stack-agnostic: pytest-cov, gcovr (C/C++), c8 or istanbul (Node/TypeScript),
and most other tools can write Cobertura XML.

Usage: check_coverage.py coverage.xml --min 80 --name firmware
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET


def line_coverage(path):
    root = ET.parse(path).getroot()
    valid = root.get("lines-valid")
    covered = root.get("lines-covered")
    if valid is not None and covered is not None:
        return int(covered), int(valid)
    # Fall back to counting <line> elements.
    lines = root.findall(".//line")
    return sum(1 for ln in lines if int(ln.get("hits", "0")) > 0), len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--min", type=float, default=80.0)
    ap.add_argument("--name", default="component")
    args = ap.parse_args()

    covered, valid = line_coverage(args.report)
    if valid == 0:
        print(f"::error::{args.name}: the coverage report measured 0 lines. "
              "Tests did not run or the source is not being measured.")
        return 1
    pct = 100.0 * covered / valid
    msg = f"{args.name}: line coverage {pct:.1f}% ({covered}/{valid}), minimum {args.min:.0f}%"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Coverage\n{msg}\n")
    if pct < args.min:
        print(f"::error::{msg} - below the minimum")
        return 1
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
