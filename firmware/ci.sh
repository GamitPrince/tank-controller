#!/usr/bin/env bash
# CI for the firmware component (ADR-0003: Zephyr 4.5.0, C11, ztest + Twister
# on native_sim, gcovr).
#
# Contract (scripts/ci/run-component.sh): build, lint, run the unit tests, and
# write coverage.xml in Cobertura format in this folder. The caller runs this
# script with the working directory set to firmware/ and then enforces the 80%
# line-coverage minimum itself.
#
# Run it by hand the same way CI does, from the repository root:
#   bash scripts/ci/run-component.sh firmware
# On Windows that needs WSL2 (AGENTS.md section 3); CI runs it on Ubuntu.
#
# The Zephyr tree and its modules are fetched into the west workspace whose
# root is the repository root, where .gitignore already blocks zephyr/,
# modules/ and .west/. They are never committed.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
TWISTER_OUT="${TWISTER_OUT:-twister-out}"
# native_sim's 64-bit variant avoids needing 32-bit multilib on the runner.
BOARD="${BOARD:-native_sim/native/64}"

FIRMWARE_DIR="$(pwd)"
WORKSPACE_DIR="$(cd .. && pwd)"
# The link library both boards build (S-056). This job formats, checks, tests
# and measures it, so the ESP32 job does not count it twice.
SHARED_LINK_DIR="$WORKSPACE_DIR/shared/link-protocol"
# cppcheck severities (S-057). Errors are always reported and always block.
CPPCHECK_BLOCKING="warning,portability"
CPPCHECK_ADVISORY="style,performance"

log() { echo "==> $*"; }

venv_python() {
	if [ -x "$VENV_DIR/bin/python" ]; then
		echo "$FIRMWARE_DIR/$VENV_DIR/bin/python"
	else
		echo "$FIRMWARE_DIR/$VENV_DIR/Scripts/python.exe"
	fi
}

install_build_tools() {
	local py="$1"
	log "Installing west and gcovr"
	"$py" -m pip install --quiet --upgrade pip
	"$py" -m pip install --quiet -r requirements-dev.txt
}

# Creates the west workspace at the repository root if it is not there yet,
# using firmware/west.yml as the manifest so the pinned Zephyr revision has a
# single source.
fetch_zephyr() {
	local py="$1"
	if [ ! -d "$WORKSPACE_DIR/.west" ]; then
		log "Initialising the west workspace at $WORKSPACE_DIR"
		(cd "$WORKSPACE_DIR" && "$py" -m west init -l firmware)
	fi
	log "Fetching Zephyr and its modules (shallow)"
	(cd "$WORKSPACE_DIR" && "$py" -m west update --narrow --fetch-opt=--depth=1)
}

# Twister needs more than the base set: natsort, psutil and friends live in
# the build-test and run-test files. The full requirements.txt also pulls the
# documentation toolchain, which this job does not need.
install_zephyr_requirements() {
	local py="$1"
	local name
	for name in base build-test run-test; do
		local file="$ZEPHYR_BASE/scripts/requirements-$name.txt"
		if [ ! -f "$file" ]; then
			echo "::warning::$file is missing; skipping it."
			continue
		fi
		log "Installing Zephyr's $name Python requirements"
		"$py" -m pip install --quiet -r "$file"
	done
}

check_formatting() {
	if ! command -v clang-format >/dev/null 2>&1; then
		echo "::warning::clang-format is not installed; skipping the format check."
		return 0
	fi
	log "Checking formatting with clang-format"
	find src tests app -name '*.c' -o -name '*.h' | xargs clang-format --dry-run -Werror
	find "$SHARED_LINK_DIR" -name '*.c' -o -name '*.h' |
		xargs clang-format --style="file:$FIRMWARE_DIR/.clang-format" --dry-run -Werror
}

# cppcheck (ADR-0003 decision 7), blocking since S-057. Errors, warnings and
# portability findings fail the job; style and performance findings are
# printed for the reviewer and do not. A suppression is inline, next to the
# code it hides and with its reason, so it is reviewed with that code.
# CI installs cppcheck, so a missing one fails there and only warns locally.
run_cppcheck() {
	if ! command -v cppcheck >/dev/null 2>&1; then
		if [ "${GITHUB_ACTIONS:-}" = true ]; then
			echo "::error::cppcheck is not installed; the firmware CI job must install it."
			return 1
		fi
		echo "::warning::cppcheck is not installed; skipping static analysis (CI runs it)."
		return 0
	fi
	log "Running $(cppcheck --version): blocking on $CPPCHECK_BLOCKING"
	cppcheck --std=c11 --enable="$CPPCHECK_BLOCKING" --error-exitcode=1 --inline-suppr \
		--quiet src app/src "$SHARED_LINK_DIR"
	log "cppcheck $CPPCHECK_ADVISORY findings (advisory, not blocking)"
	cppcheck --std=c11 --enable="$CPPCHECK_ADVISORY" --inline-suppr --quiet src app/src \
		"$SHARED_LINK_DIR"
}

run_tests() {
	local py="$1"
	log "Running the ztest suites on $BOARD with coverage"
	rm -rf "$TWISTER_OUT"
	"$py" "$ZEPHYR_BASE/scripts/twister" \
		--testsuite-root tests \
		--testsuite-root app \
		--platform "$BOARD" \
		--outdir "$TWISTER_OUT" \
		--coverage \
		--coverage-tool gcovr \
		--inline-logs
}

# ADR-0003 decision 10: coverage counts all our firmware code, including the
# hardware layer. Only Zephyr, third-party and generated code are excluded,
# which the filters below express by including src/ and the shared link
# library and nothing else.
write_coverage_report() {
	local py="$1"
	log "Writing Cobertura coverage.xml"
	"$py" -m gcovr \
		--root "$WORKSPACE_DIR" \
		--filter "$FIRMWARE_DIR/src/" \
		--filter "$SHARED_LINK_DIR/" \
		--cobertura coverage.xml \
		--print-summary \
		"$TWISTER_OUT"
}

main() {
	rm -f coverage.xml
	"$PYTHON" -m venv "$VENV_DIR"
	local py
	py="$(venv_python)"
	# Twister shells out to gcovr by name, so the virtual environment's
	# scripts must be on PATH for child processes, not just importable.
	PATH="$(dirname "$py"):$PATH"
	export PATH

	install_build_tools "$py"
	fetch_zephyr "$py"

	export ZEPHYR_BASE="$WORKSPACE_DIR/zephyr"
	export ZEPHYR_TOOLCHAIN_VARIANT="${ZEPHYR_TOOLCHAIN_VARIANT:-host}"

	install_zephyr_requirements "$py"
	check_formatting
	run_cppcheck
	run_tests "$py"
	write_coverage_report "$py"

	log "Wrote $FIRMWARE_DIR/coverage.xml"
}

main "$@"
