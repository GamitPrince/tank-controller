# AGENTS.md — Tank-AI project rules for coding agents

Read this file completely at the start of every session. It is the standing brief for Tank-AI (AI-assisted smart tank controller, repo `GamitPrince/tank-controller`).
Last updated: 20 Nov 2026. Source of truth for decisions is the ADRs in `docs/adr/` once pushed, then the per-feature spec you are given. If this file and a spec disagree, STOP and ask.

---

## 0. How you work here

1. You only work from a **feature spec** (`docs/stories/S-0xx-name.md`) that belongs to a GitHub story issue `S-0xx`. No spec, no story issue: no work. Do not "set up the whole project" in one go; scaffold only what the current spec asks for.
2. Before editing: `git status`, `git config user.email` (must be `princ3gamit20561@gmail.com`, user.name `GamitPrince`), and `git pull` on `develop`.
3. Branch from `develop`: `feature|bugfix|hotfix/S-0xx-short-description`. Never push to `main` or `develop`; the rulesets reject it.
4. Small commits `type(scope): description`. PRs under about 300 changed lines; split bigger work.
5. Open the PR with the template, `Closes #N`, all 7 checklist items ticked honestly. Do not tick an item you did not do.
6. If anything is unclear, unsafe, or outside the spec, ask. Never guess on safety, phase, or hardware.
7. Never disable, skip, or weaken a CI check, ruleset, CODEOWNERS entry, or test to get green.
8. At the end of a task, report: what changed, what was tested and how, what was NOT done, and any assumption made (mark assumptions `[Confirm]` in code comments or the PR).

## 1. Hard rules (safety and phase)

- **Phase 1 = read-only monitoring of level and temperature only.** No control, no actuation, no AI/analytics, no other sensors (vibration, noise, exhaust, fuel, power are Phase 2), nothing wired into the hardwired safety chain.
- The hardwired safety chain (high-high level trip, low-low heater cut-off, over-temperature trip, emergency stop, pump dry-run, fire/gas) is only ever **read** as status-only digital inputs. Never write code or design a path that outputs to it. All interface designs are input-only.
- If a request touches trips, interlocks, safe states, watchdog, or would blur a phase boundary: stop and ask before building.
- Changes in `firmware/src/safety/` or `docs/safety/` need the EE's approval (CODEOWNERS) and the `safety` label. Any defect in a safety function is Critical.
- The dashboard is read-only for plant data. It never sends commands to devices. The controller is send-only (devices publish; the cloud never commands them in Phase 1).
- Phases: 1 sense/transmit/see; 2 control + new sensors + diagnostics + carbon; 3 predictive heating/energy optimisation; 4 fleet intelligence. (These are not the playbook's 12 SDLC phases.)

## 2. Team and GitHub identities

| User | Role |
|---|---|
| GamitPrince | Owner, project manager / tech lead, the only firmware developer, ESP32/cloud work. Final authority over the repo (ADR-0009 rule 7, NOT yet applied in GitHub) |
| prinz-assists | Collaborator with Write access. May approve PRs. |
| gamitriyan-del | Electrical engineer (EE): owns `hardware/` and safety approvals. (Older notes say `riyangamit-del`; the correct handle is `gamitriyan-del`.) |

Active team: GamitPrince (owner, tech lead), gamitriyan-del (EE), prinz-assists. Former contributors ArkinGamit and SHINE-18 left the project on 20 Nov 2026 and their invitations were cancelled. Who builds the dashboard is [Confirm]. QA sign-off owner: not assigned.

## 3. Repository rules (live today)

- Public repo, default branch `develop`. Rulesets on `main` and `develop` (no bypass actors yet): no direct push, PR required, 1 approval from a non-author, approval of the latest push, stale approvals dismissed, code-owner review, conversations resolved, squash merge only, linear history, branch up to date, required checks `ci-gate`, `pr-policy`, `interfaces-review`. Version tags `v*.*.*` protected.
- CODEOWNERS: `firmware/src/safety/`, `docs/safety/` = EE only (`@gamitriyan-del`). `interfaces/`, `.github/` and `scripts/` = `@GamitPrince` and `@prinz-assists`. One approval from a collaborator other than the author satisfies code-owner and interfaces review.
- `pr-policy` checks: PR title `type(scope): description` (types feat fix docs style refactor test chore perf; scopes firmware gateway dashboard simulator hardware interfaces docs); branch `feature|bugfix|hotfix/S-xxx-...` or `release/vX.Y.Z` (no `docs/` or other prefixes); `Closes #N` pointing at an open issue titled `S-xxx: ...` with a `story`, `bug` or `chore` label; all 7 checklist items ticked; `safety` label on safety paths; PRs into `main` update `CHANGELOG.md`; no secrets or build files. Only `release/*` and `hotfix/*` target `main`.
- **pr-policy facts (verified by reading `.github/workflows/pr-policy.yml`):** only the keywords `close(s/d)`, `fix(es/ed)` and `resolve(s/d)` followed by `#N` count as a story link; **`Refs #N` is NOT accepted**. The linked issue must be open, must not be a PR, must have a `story`, `bug` or `chore` label, and its title must start with the same `S-xxx` as the branch. Merging closes the linked issue (default branch is `develop`), so one issue cannot cover several PRs. Issues and PRs share one number sequence on GitHub (issue #1 = S-001, PR #2 = the practice PR), so S-002 is NOT issue #2; look the number up with `gh issue list`. Do not edit `pr-policy.yml` (CODEOWNERS policy file); the tech lead decides how to handle multi-PR stories.
- **PR title scope:** `docs(docs): ...` is valid; `docs(adr): ...` is NOT (scope `adr` is not in the allowed list) and fails `pr-policy`. Any older note that says `docs(adr)` is wrong.
- **80% line-coverage gate:** each component needs `<component>/ci.sh` that builds, lints, tests, and writes `coverage.xml` (Cobertura). A folder containing code but no `ci.sh` fails CI. Check scripts: `scripts/check_coverage.py`.
- GitHub Actions are restricted to **GitHub-owned actions only**; third-party actions (for example the AWS credentials action, Terraform setup actions) are blocked until the tech lead allows them. Use `run:` steps or ask.
- Squash merge, branch auto-deleted. Never commit: secrets, `.env`, keys, certificates, `.elf/.bin`, `node_modules`, the full vendor SDK, large datasets, **real customer data**, **hardware schematics or hardware review records** (decided 19 Nov: they live in a private location, not this public repo).
- Environment: developers use Windows with PowerShell and VS Code. Run `.sh` scripts in Git Bash. **Known issue:** the repo's line-ending file is committed as `gitattributes` (no leading dot), so Git ignores it and Windows checkouts get CRLF; `git status` then shows about 23 tracked files as modified although only line endings differ. Never commit those; never use `git add -A`, `git commit -a`, `git stash` or `git reset` to "clean up" without asking. The fix (rename to `.gitattributes`, renormalize) is its own small chore story, not part of other work. `gh` is at `%LOCALAPPDATA%\Programs\GitHubCLI\bin`. Firmware builds use WSL2.

## 4. Architecture decisions (summary; ADR files are the detail)

Status (checked against the repo files, 19 Nov 2026): ADR-0003 to 0009 are **confirmed by the tech lead** (17-19 Nov 2026) and exist as untracked files in the tech lead's local `docs/adr/`, but are **not yet committed or pushed and not yet Accepted** (an ADR becomes Accepted when its PR gets one approval from gamitriyan-del or prinz-assists (decided by the tech lead 20 Nov 2026; the author cannot approve their own PR). On 20 Nov 2026 the tech lead extended this to the whole project: one approval from a collaborator other than the author is enough for every PR, including `interfaces/`, `.github/` and `scripts/`. Safety paths (`firmware/src/safety/`, `docs/safety/`) keep the EE's approval unless the tech lead says otherwise [Confirm]. Story S-010 merged on 20 Nov 2026 (PR #19), so GitHub now enforces this one-non-author-approval rule: CODEOWNERS lists `@GamitPrince @prinz-assists` on `interfaces/`, `.github/` and `scripts/`, the `interfaces-review` check accepts one approval from any collaborator other than the author, and the repository variable `INTERFACE_REVIEWERS` is `GamitPrince,prinz-assists`). ADR-0001 (public repo) is already in the repo as `docs/adr/0001-public-repository-on-github-free.md`, status Proposed, with out-of-date points (hardware files, tech lead authority). **ADR-0002 (hardware) is not in the folder**; it is Proposed and waits for the EE, so it is not pushed yet and you must not write it. `docs/adr/README.md` (index), `template.md` and `PUSH-GUIDE.md` also exist locally; `PUSH-GUIDE.md` contains a wrong PR-title scope (`docs(adr)`) and an unverified `Refs` suggestion, so do not follow it or push it. Until the ADR files are merged into `docs/adr/`, treat this table as the working decision record. Do not re-decide these; if a spec seems to contradict one, ask.

| ADR | Topic | Decisions |
|---|---|---|
| 0002 | Hardware | Controller = NXP FRDM-MCXN947 (evaluation board, goes to the pilot site; EE checks enclosure, about 50 C ambient, IP65). Three EE-designed input-only interfaces: 6-channel MAX31865 for 3-wire PT100 (shared SPI, six chip selects); AD4111 4-20 mA (two of four channels used); 16-channel optocoupler digital inputs (status-only). RS-485 not needed in Phase 1. Power/protection, pin mapping, enclosure still with the EE. ESP32-S3 + A7672S board gives Wi-Fi and 4G (specs not verified). |
| 0003 | Firmware | Zephyr RTOS, **4.5.0 pinned**, language C (C11). Tests: ztest + Twister on native_sim + gcovr. WSL2 on Windows, CI on Ubuntu. `-Werror`, clang-format, cppcheck (MISRA revisited in Phase 2). Four layers: hardware, measurement, record, communications. Safety-status reads only in `firmware/src/safety/`. Own small AD4111 SPI module. Coverage counts all firmware code including the hardware layer. Fallback if early hardware check fails: FreeRTOS with the NXP MCUXpresso SDK. |
| 0004 | Communications | 1 No separate gateway: the FRDM collects and communicates itself. 2 Ethernet or Wi-Fi primary (client decides), 4G backup. 3 ESP32 = comms helper; FRDM keeps data and buffer. 4 FRDM-ESP32 link = UART. 5 Own framed protocol (COBS, sequence numbers, CRC, delivery confirmation), shared C library. 6 CBOR records, CDDL schema in `interfaces/`. 7 MQTT over TLS, QoS 1, per-device certificates, outbound only (WebSocket on 443 if 8883 blocked). 8 Two-tier failover, about 10 s without cloud ack (configurable). 9 Versioned YAML signal list with numeric IDs replaces the register map. 10 Volume/mass computed in the cloud; controller send-only. 11 SNTP plus boot-relative time with boot ID and "time not yet known" flag. 12 Compact lossless append-only flash log with delta encoding (SD card fallback). 13 Standalone Python simulator (same schema and signal list, one command, fault injection, outage replay with original timestamps). |
| 0005 | Security | Per-device key made on the board, never leaves. QR code carries ONLY the device ID; an admin claims it once and assigns it to a tank. Own private CA (key offline, encrypted backup). Firmware signing key (separate from CA) in the GitHub pipeline with safeguards. Outbound-only TLS, no VPN in Phase 1. ESP32 has its own cert from the same CA. Certificates about 5 years, manual renewal, broker block list. Signed boot, debug port locked on site units. Rules: no secrets in the public repo, secret scanning + push protection on, each device publishes only to its own topic. |
| 0006 | ESP32 firmware | ESP-IDF, C, Unity tests + gcovr (80% gate on our logic; thin wrappers over Wi-Fi/modem/TLS/MQTT excluded and covered by recorded bench tests). Secure boot + flash encryption on site units, own ESP32 signing key. A7672S as PPP connection with the same TLS/MQTT. |
| 0007 | Cloud | Managed AWS services; IoT Core as broker with our own CA; one shared multi-tenant cloud in our account (customer > plant > tank > device); Tiger Cloud (managed TimescaleDB) on AWS Mumbai for readings and records (fallback: Timestream for InfluxDB 3 + managed PostgreSQL); retention: raw archive forever, per-minute summaries forever, per-second 90 days; backend in containers fed by a managed queue, decodes CBOR; Phase 1 firmware updates by cable only. Rules: encryption in transit and at rest; calculation version stored; monthly cost budget and alert. **THREE GATES before any cloud account is opened or paid for:** customers' answers (Siemens/Astec), an early cloud test, a Tiger Cloud quote. |
| 0008 | Backend and dashboard | Python (FastAPI) backend; TypeScript/React dashboard; OpenAPI with generated TS types. Login = Amazon Cognito Essentials. User belongs to one customer, optionally limited to plants/tanks; roles operator, maintenance, admin (customer's), service (our staff, audited); backend checks every request. No technician role: each technician has a **named admin account**, never shared. Audit trail = append-only table + daily write-once S3 copy (Object Lock). Live updates by server-sent events with polling fallback; quality flag and age on every value; browser never talks to the broker. pytest + Vitest, 80% gate counts all code including screens; Playwright e2e not counted. Static SPA on AWS storage + CDN. Design: colour plus text, tablet usable with gloves. |
| 0009 | CI and deployment | Terraform or OpenTofu for cloud blueprints; two copies (test, live); GitHub Actions: merge to `develop` deploys to test, release tag from `main` deploys to live after approval in a GitHub environment, rollback = redeploy previous tag; AWS login by short-lived OIDC roles (no permanent keys); AWS built-in monitoring with "no data from device" alert; free GitHub security set on each PR (Dependabot, secret scanning, CodeQL, image scan), High/Critical block merge. Rule 7: tech lead authority (bypass list), not yet applied. |

## 5. Plant facts (confirmed)

- Heat source: diesel-fired burner heating the mixture in the baghouse; exhaust goes through an existing filtered chimney (exhaust sensors are Phase 2, above the filter). No burner return line (single fuel flow meter, Phase 2). No hazardous zones. Carbon emission is for client monitoring only. No automatic stop on severe vibration.
- Client may or may not provide Ethernet; Wi-Fi may be available. Hot, dusty, vapour-laden outdoor site, ambient up to about 50 C, enclosure IP65.
- Phase 1 signals: radar level, PT100 zone temperatures (bottom, mid, upper, heater zone, outlet, return), heater sheath/pocket and thermal-oil inlet/outlet temperatures, ambient (and wind if fitted), high-high/low-low switch status, trip status (over-temp, e-stop, pump dry-run, fire/gas where fitted). The 16 digital signal list is not yet shared; do not invent it. Sensor models and counts for Phase 2 sensors are undecided.
- Intended customers: Siemens or Astec (large industrial): fleet scale and enterprise security matter.

## 6. Repo layout and open layout questions

Existing folders from the scaffold: `firmware/`, `gateway/`, `dashboard/`, `simulator/`, `hardware/`, `interfaces/`, `docs/`, `scripts/`, `.github/`.
- **`gateway/` is probably obsolete** (ADR-0004 decision 1: no separate gateway). Do not add code there; the tech lead decides its fate in a story. CI still runs a `gateway` job, and the README, CODEOWNERS comments and story template still mention it.
- **`firmware/src/` placeholder folders do not match ADR-0003.** The scaffold has `safety/`, `drivers/`, `control/` and `analytics/`; ADR-0003 defines four layers (hardware, measurement, record, communications) plus `safety/` for status reads. `control/` and `analytics/` are Phase 2/3 and must stay empty in Phase 1. Do not reorganize these folders unless a spec says so; the firmware skeleton story (P1-01) will decide the layout.
- Not yet decided (ask, do not invent): where the ESP32 firmware lives; where the cloud backend lives (earlier assumption: under `dashboard/`); where Terraform lives and its state layout; database migration tool; container registry and versioning; topic layout and message batching interval.
- `interfaces/` holds the CDDL schema and the versioned YAML signal list. Any change needs one approval from a collaborator other than the author (S-010, merged 20 Nov 2026).

## 7. Coding standards

Follow the language style guide; no hardcoded values (constants or config), no commented-out code, no debug output left in, functions about 40 lines or fewer, single responsibility, self-documenting names, comments only for non-obvious logic, `TODO(S-0xx): ...` with a tracked story only. Unit tests for every feature; 80% line coverage; test sensor failure, network drop, out-of-range values. Never show stale data as live. Failed sensors are flagged and excluded, never silently replaced.

## 8. Definition of Done

All acceptance criteria in the spec met; tested on simulator or bench; unit tests passing at or above 80%; no open Critical/High bugs; docs and CHANGELOG updated; safety story: EE approval and test result recorded. AI-written code must still be readable and reviewed by a human; write for the reviewer.

## 9. Feature spec format (what you will receive)

Each spec at `docs/stories/S-0xx-name.md` contains: story ID and title, goal, phase check, component(s), review flags (EE / one non-author collaborator), decisions already made (with ADR references), files to create or change, interfaces touched, acceptance criteria, test plan (simulator or bench), out of scope, open questions `[Confirm]`, and PR checklist notes. Implement exactly that. If the spec is missing any of these, ask before coding.

## 10. Current state and first tasks

Done: repo scaffold, rulesets, labels, Sprint 1-4 milestones, CI workflows, Git identity fixed, GitHub CLI authenticated, practice story S-001 / PR #2 (green, waiting for one approval from gamitriyan-del or prinz-assists).
Not done: invitations accepted; real story issues (S-002 = P1-00 tech-stack ADRs; other P1-xx map to S-xxx when created); ADRs pushed; component `ci.sh` files; story cards and RSD updated for ADR consequences; hardware sign-off with the EE.
Local repo state seen in the zip (19 Nov 2026): checked out on `feature/S-001-practice-pr` (not `develop`), 23 tracked files show as modified because of CRLF line endings only, ADR-0003 to 0009 untracked. The practice PR #2 is not merged yet, so `develop` does not contain it.
Order: (1) ADR PRs, one per ADR, only after the tech lead settles how issues are linked (see `pr-policy` facts in section 3); (2) story issues; (3) Sprint 1: repo/CI skeleton, simulator, signal list, first sensor reads. The early cloud test comes before any cloud account is opened.

## 11. Things you must not do

Do not push to `main`/`develop`; do not open cloud accounts or add paid services; do not commit hardware files, secrets or customer data; do not edit CODEOWNERS, rulesets, `.github/workflows/*`, or `pr-policy` unless a spec explicitly says so; do not add third-party GitHub Actions; do not add Phase 2 features early; do not edit the RSD or story cards (they are Claude Docs owned by the project manager); do not install packages or tools globally without saying so.
