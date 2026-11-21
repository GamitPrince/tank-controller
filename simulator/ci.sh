#!/usr/bin/env bash
# CI for the simulator component (ADR-0004 decision 13: standalone Python).
#
# Contract (scripts/ci/run-component.sh): build, lint, run the unit tests, and
# write coverage.xml in Cobertura format in this folder. The caller runs this
# script with the working directory set to simulator/ and then enforces the
# 80% line-coverage minimum itself.
#
# Run it by hand the same way CI does, from the repository root:
#   bash scripts/ci/run-component.sh simulator
#
# On Windows, "python3" is often a Microsoft Store stub. Override the
# interpreter instead of editing this script:
#   PYTHON=python bash scripts/ci/run-component.sh simulator
set -euo pipefail

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

log() { echo "==> $*"; }

create_environment() {
  log "Creating the virtual environment with $PYTHON"
  "$PYTHON" -m venv "$VENV_DIR"
}

# The venv layout differs between Windows and POSIX.
venv_python() {
  if [ -x "$VENV_DIR/bin/python" ]; then
    echo "$VENV_DIR/bin/python"
  else
    echo "$VENV_DIR/Scripts/python.exe"
  fi
}

install_dependencies() {
  local py="$1"
  log "Installing pinned development dependencies"
  "$py" -m pip install --quiet --upgrade pip
  "$py" -m pip install --quiet -r requirements-dev.txt
  # Editable install so tests import tanksim the same way a consumer would.
  "$py" -m pip install --quiet -e .
}

lint() {
  local py="$1"
  log "Linting"
  "$py" -m ruff check .
  "$py" -m ruff format --check .
}

run_tests() {
  local py="$1"
  log "Running the unit tests with coverage"
  "$py" -m pytest --cov --cov-report="xml:coverage.xml" --cov-report=term-missing
}

main() {
  rm -f coverage.xml
  create_environment
  local py
  py="$(venv_python)"
  install_dependencies "$py"
  lint "$py"
  run_tests "$py"
  log "Wrote $(pwd)/coverage.xml"
}

main "$@"
