# Contributing

Rules from the GitHub Workflow Guide, enforced by the repository settings. A pull request that breaks one cannot be merged.

## Flow

1. Pick a story card (GitHub issue titled `S-019: ...`). No story card, no work.
2. Branch from the latest `develop`: `feature/S-019-level-control` (also `bugfix/`, `hotfix/`, `release/v0.1.0`).
3. Commit small and often: `type(scope): description`, for example `feat(firmware): add level control loop`. Types: feat fix docs style refactor test chore perf. Scopes: firmware gateway dashboard simulator hardware interfaces docs.
4. Open a pull request into `develop` with the same style of title, `Closes #19` in the description, and the checklist ticked. Keep it under about 300 changed lines.
5. Wait for CI to go green and for one reviewer who is not you. Fix review comments on the same branch.
6. The reviewer approves; you squash-merge. The branch is deleted automatically.

Never push directly to `main` or `develop`. Never disable a check to get a pull request through.

## Extra approvals

| You changed | Who must approve |
| --- | --- |
| `firmware/src/safety/` or `docs/safety/` (trips, interlocks, safe states, watchdog) | The EE. Add the `safety` label |
| `interfaces/` | All three developers (the author counts as one) |
| `.github/` or `scripts/` | Another code owner listed in `.github/CODEOWNERS` (never yourself) |

## CI contract for each component

Each of `firmware/`, `gateway/`, `dashboard/` and `simulator/` gets a `ci.sh` once its stack is chosen. It must build, lint, run the unit tests and write `coverage.xml` (Cobertura format) in that folder. CI fails if line coverage is below 80%. A folder with code but no `ci.sh` fails CI.

## Never commit

Secrets or credentials, the full vendor SDK, build output, large files, real customer data. If a secret is committed by accident, tell the tech lead immediately; deleting it in a later commit is not enough.
