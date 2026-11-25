#!/usr/bin/env bash
# CI for the ESP32 component (ADR-0006: ESP-IDF, C, Unity, gcovr).
#
# Contract (scripts/ci/run-component.sh): build, lint, run the unit tests, and
# write coverage.xml in Cobertura format in this folder. The caller runs this
# script with the working directory set to esp32/ and then enforces the 80%
# line-coverage minimum itself.
#
# Run it by hand the same way CI does, from the repository root:
#   bash scripts/ci/run-component.sh esp32
#
# The logic is standard C and is tested on the host with Unity, as ADR-0006
# decision 3 says; ESP-IDF is not needed for that. Building the real ESP32
# image in CI arrives with the first ESP-IDF code (S-047 spec, item 4).
# Unity is fetched at a pinned tag into build/, which .gitignore blocks; it is
# never committed.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
UNITY_TAG="${UNITY_TAG:-v2.6.1}"
UNITY_URL="https://github.com/ThrowTheSwitch/Unity.git"
BUILD_DIR="${BUILD_DIR:-build/host-tests}"
UNITY_DIR="build/unity-$UNITY_TAG"

ESP32_DIR="$(pwd)"
# One .clang-format for all our C, kept with the FRDM firmware.
CLANG_FORMAT_STYLE="file:$ESP32_DIR/../firmware/.clang-format"

log() { echo "==> $*"; }

venv_python() {
	if [ -x "$VENV_DIR/bin/python" ]; then
		echo "$ESP32_DIR/$VENV_DIR/bin/python"
	else
		echo "$ESP32_DIR/$VENV_DIR/Scripts/python.exe"
	fi
}

install_tools() {
	local py="$1"
	log "Installing gcovr"
	"$py" -m pip install --quiet --upgrade pip
	"$py" -m pip install --quiet -r requirements-dev.txt
}

fetch_unity() {
	if [ -f "$UNITY_DIR/src/unity.c" ]; then
		return 0
	fi
	log "Fetching Unity $UNITY_TAG"
	rm -rf "$UNITY_DIR"
	git clone --quiet --depth 1 --branch "$UNITY_TAG" "$UNITY_URL" "$UNITY_DIR"
}

check_formatting() {
	if ! command -v clang-format >/dev/null 2>&1; then
		echo "::warning::clang-format is not installed; skipping the format check."
		return 0
	fi
	log "Checking formatting with clang-format"
	find components tests -name '*.c' -o -name '*.h' |
		xargs clang-format --style="$CLANG_FORMAT_STYLE" --dry-run -Werror
}

build_and_test() {
	log "Building the host tests"
	rm -rf "$BUILD_DIR"
	cmake -S tests -B "$BUILD_DIR" -DUNITY_DIR="$ESP32_DIR/$UNITY_DIR"
	cmake --build "$BUILD_DIR"
	log "Running the Unity tests"
	ctest --test-dir "$BUILD_DIR" --output-on-failure
}

# Only esp32/ code counts here. The shared link library is measured by the
# firmware job, so it is not counted twice.
write_coverage_report() {
	local py="$1"
	log "Writing Cobertura coverage.xml"
	"$py" -m gcovr \
		--root "$ESP32_DIR" \
		--filter "$ESP32_DIR/components/" \
		--cobertura coverage.xml \
		--print-summary \
		"$BUILD_DIR"
}

main() {
	local py
	rm -f coverage.xml
	"$PYTHON" -m venv "$VENV_DIR"
	py="$(venv_python)"
	install_tools "$py"
	fetch_unity
	check_formatting
	build_and_test
	write_coverage_report "$py"
	log "Wrote $ESP32_DIR/coverage.xml"
}

main "$@"
