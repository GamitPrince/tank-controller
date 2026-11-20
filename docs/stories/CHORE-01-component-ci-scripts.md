# CHORE-01: Component `ci.sh` scripts and minimal buildable skeletons

- Story ID: `[Confirm]` — not yet issued. This is a **repo chore**, not a Phase 1 feature story, so it has no `P1-xx` ID from the story card.
- Points: **5 (proposed)**. Priority: Must — **blocks the first code story.**
- Component: firmware, simulator, scripts. Review flag: none (does not touch `interfaces/` or safety paths).

## Goal
Give each component a `ci.sh` that builds, lints, tests and writes a Cobertura `coverage.xml`, so the 80% gate actually measures something and the first code story is not also a CI-bootstrapping story.

## Phase check
Build tooling only. No plant signals, no safety function, no phase boundary.

## Why this is its own story
`CONTRIBUTING.md` promises a `ci.sh` per component and the 80% line-coverage gate. **No component has one.** The folders are empty, so `ci-gate` passes today and the debt is invisible — but it lands on whoever writes the first line of code.

It also closes **P1-00 acceptance criterion 4**, "a minimal skeleton in each layer builds in CI", which is the only part of P1-00 still unmet, and the residual item on **P1-01**.

## What already exists — do not rebuild it
The CI harness is complete. This chore only supplies the per-component scripts.

- **`.github/workflows/ci.yml`** runs a job per component, gated by a `changes` job, and always reports `ci-gate`.
- **`scripts/ci/run-component.sh <component>`** is the contract:
  - If `<component>/ci.sh` exists: deletes any stale `coverage.xml`, runs `cd <component> && bash ./ci.sh`, **requires** `<component>/coverage.xml` afterwards, then enforces the minimum.
  - If it does not exist: **passes** when the folder holds only `.gitkeep` and `*.md`, and **fails** as soon as any other file appears.
- **`scripts/check_coverage.py`** parses Cobertura, defaults to 80% (`COVERAGE_MIN`), writes to the step summary, and **fails when the report measures 0 lines**.

**Consequences for how this chore must be done:**
1. `ci.sh` runs with its working directory set to the component folder, so it writes `coverage.xml` beside itself.
2. **Adding a `ci.sh` to an empty component breaks CI.** The script would run, produce a report measuring zero lines, and `check_coverage.py` would fail. So a `ci.sh` cannot be added on its own.
3. Do not edit `run-component.sh`, `check_coverage.py` or `ci.yml` except where this spec says so.

## Scope decision `[Confirm]`
Because of consequence 2, there are two ways to do this, and they are genuinely different stories:

- **Option A (recommended): `ci.sh` plus a minimal real skeleton per component.** Each component gets one trivial source module and one passing test, so coverage is measurable and above 80%, and CI genuinely exercises the toolchain. This is also exactly what P1-00 criterion 4 asks for. Cost: a little throwaway code that the first feature story replaces.
- **Option B: defer each `ci.sh` into the pull request that brings that component's first code.** Nothing is added early, but the first code story then also has to stand up a toolchain in CI, which is a poor place to discover that the Zephyr build does not fit the job timeout.

This spec is written for **Option A**.

## Components in scope
Only the two that the next stories need:

| Component | Toolchain | ADR |
| --- | --- | --- |
| `firmware/` | Zephyr 4.5.0, C11, ztest + Twister on `native_sim`, gcovr to Cobertura, `-Werror`, clang-format, cppcheck | ADR-0003 |
| `simulator/` | Python, pytest with coverage to Cobertura, lint | ADR-0004 decision 13 |

**Out of scope, deliberately:**
- **`gateway/`** — obsolete under ADR-0004 decision 1. It has no code, so it passes without a `ci.sh`. **Do not write one**; its fate is a separate decision.
- **`dashboard/`** (Vitest, ADR-0008) and the **backend** (pytest, ADR-0008) — no code yet, and **where the backend lives is undecided**.
- **ESP32 firmware** (Unity + gcovr, ADR-0006) — **where it lives is undecided**.

Each of those gets its own `ci.sh` in its own story once its code and location exist.

## Coverage exclusions to encode
Per the ADRs, so the gate measures the right thing:
- **Firmware (ADR-0003 decision 10):** counts **all our firmware code including the hardware layer**. Excludes only Zephyr itself, third-party and generated code. Hardware-layer coverage comes from simulated chips on `native_sim`.
- **ESP32 (ADR-0006), later:** thin Wi-Fi, modem, TLS and MQTT wrappers excluded, covered by recorded bench tests instead.
- Any change to an exclusion list needs a reviewer's approval.

## Risks to settle while doing this
1. **The `firmware` job has `timeout-minutes: 15`.** Installing the Zephyr SDK, running `west`, building and running Twister may exceed that on a cold run. If it does, the timeout must rise — that is a `.github/workflows/ci.yml` edit, which `AGENTS.md` section 11 forbids without explicit permission. **Ask before editing it.**
2. **Third-party GitHub Actions are blocked.** The Zephyr SDK must be installed with `run:` steps. `actions/cache` is GitHub-owned and therefore allowed, which matters because an uncached SDK download on every PR is slow.
3. **CI runs Ubuntu; developers build firmware in WSL2.** `ci.sh` must work in both and assume no developer-machine state.

## Files to create or change
- `firmware/ci.sh`, plus a minimal module and one ztest case.
- `simulator/ci.sh`, plus a minimal module and one pytest case.
- `CONTRIBUTING.md` if the CI contract wording needs tightening `[Confirm]`.
- `.github/workflows/ci.yml` **only** if risk 1 forces a timeout change, and only after asking.

## Acceptance criteria
- `bash scripts/ci/run-component.sh firmware` and `... simulator` both pass locally and in CI.
- Each writes a Cobertura `coverage.xml` measuring **more than zero lines**, at **80% or above**.
- Firmware coverage includes the hardware layer; only Zephyr, third-party and generated code are excluded.
- `ci-gate` stays green, and no existing check is weakened, skipped or edited to achieve it.
- `gateway/` still passes with no `ci.sh`.
- A later pull request that adds a source file with no test visibly drops coverage below the gate — proving the gate works rather than assuming it.

## Test plan
Run both scripts locally in Git Bash and WSL2, then on a pull request. Deliberately break each one to prove the gate bites: delete the test and confirm the "0 lines" failure; add an uncovered file and confirm the sub-80% failure. Record both results in the pull request.

## Dependency
None. **Should be done before the first code story** — P1-03 produces no code, so it can go first or second, but P1-05, P1-06 and P1-27 all need this in place.

## Out of scope
Any plant signal or feature logic. The `gateway/` decision. Dashboard, backend and ESP32 scripts. Changing the 80% threshold.

## Open questions
- `[Confirm]` Option A or Option B above.
- `[Confirm]` Story points — 5 proposed, mostly for the Zephyr-in-CI work.
- `[Confirm]` Permission to raise `timeout-minutes` on the firmware job if the Zephyr build needs it.
- `[Confirm]` Is a throwaway skeleton acceptable in `firmware/`, given `firmware/src/` placeholder layout is still undecided and ADR-0003's four layers are not yet scaffolded?
