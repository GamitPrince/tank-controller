#!/usr/bin/env bash
# Runs CI for one component: firmware, gateway, dashboard or simulator.
#
# Contract for each component (decided in the tech-stack ADRs, story P1-00):
#   <component>/ci.sh   builds, lints, runs the unit tests, and writes
#                       <component>/coverage.xml (Cobertura format).
# This script then enforces the coverage minimum (default 80%).
#
# While a component has no code yet, it passes. As soon as it has any file
# other than a placeholder or Markdown, it MUST have a ci.sh, so a component
# can never go untested without anyone noticing.
set -euo pipefail

component="${1:?usage: run-component.sh <component>}"
min="${COVERAGE_MIN:-80}"

if [ ! -d "$component" ]; then
  echo "::error::Folder $component/ is missing."
  exit 1
fi

if [ -f "$component/ci.sh" ]; then
  rm -f "$component/coverage.xml"
  (cd "$component" && bash ./ci.sh)
  if [ ! -f "$component/coverage.xml" ]; then
    echo "::error::$component/ci.sh must write $component/coverage.xml (Cobertura XML)."
    exit 1
  fi
  python3 scripts/check_coverage.py "$component/coverage.xml" --min "$min" --name "$component"
else
  extra="$(find "$component" -type f ! -name '.gitkeep' ! -name '*.md' | head -n 1)"
  if [ -n "$extra" ]; then
    echo "::error::$component/ contains code (for example $extra) but has no $component/ci.sh."
    exit 1
  fi
  echo "::notice::$component/ has no code yet; nothing to build or test."
fi
