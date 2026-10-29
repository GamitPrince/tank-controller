# GitHub setup for tank-controller (SOP-SDLC-001)

For three developers and the EE, all on GitHub Free, with a public repository. Do the steps in order: the rulesets must be switched on **after** the first push, because they forbid direct pushes.

People used below:

| GitHub username | Roles |
| --- | --- |
| `GamitPrince` | Repository owner, project manager, firmware developer, gateway developer |
| `ArkinGamit` | Dashboard developer |
| `SHINE-18` | Dashboard developer |
| `gamitriyan-del` | Electrical engineer (EE) |

"All three developers" means these three people: GamitPrince, ArkinGamit and SHINE-18. Because GamitPrince writes the firmware and gateway code, his pull requests are reviewed by ArkinGamit or SHINE-18, and theirs by anyone else with write access.

## 1. Create the repository (PM)

GitHub, New repository: owner = the PM's account, name `tank-controller`, **Public**, no README, no .gitignore, no licence yet. Pick a licence deliberately before inviting outsiders: with no licence, others cannot legally reuse the code.

## 2. Push the scaffold to `main` (PM)

`.github/CODEOWNERS` already contains the real usernames. Open it once and check the spelling.

```bash
cd tank-controller
git init -b main
git add .
git commit -m "chore(docs): add repository scaffold, CI and review rules"
git remote add origin https://github.com/GamitPrince/tank-controller.git
git push -u origin main
```

This is the only direct push to `main`.

## 3. Create `develop` (PM)

```bash
git push origin main:develop
```

## 4. Invite everyone (PM)

Settings, Collaborators, Add people: `ArkinGamit`, `SHINE-18`, `gamitriyan-del`. On a personal account every collaborator has write access and cannot change settings. Each person must accept the email invitation, or CODEOWNERS will ignore them.

## 5. Apply the settings (PM, GitHub CLI logged in as the owner)

```bash
gh auth login
scripts/setup-github.sh GamitPrince/tank-controller "GamitPrince,ArkinGamit,SHINE-18"
```

The second argument is the three people who must all review changes to `interfaces/`. The script refuses to run unless they are three different people.

The script is safe to re-run. It sets what the table below lists. The same settings can be made by hand if the script fails.

| Setting (Settings page) | Value |
| --- | --- |
| General, Default branch | `develop` (so "Closes #19" auto-closes the story; GitHub only does that on the default branch) |
| General, Pull requests | Allow squash merging **on**; merge commits **off**; rebase merging **off**; squash commit message "Default to pull request title"; always suggest updating PR branches **on**; auto-delete head branches **on**; auto-merge **off** |
| General, Features | Issues on, Projects on, Wikis off |
| Rules, Rulesets | Import `.github/rulesets/protect-main-develop.json` and `protect-version-tags.json` (enforcement Active, bypass list empty) |
| Actions, General | Allow GitHub-owned actions only; workflow token read-only; do not let Actions approve pull requests; approval required for outside contributors' workflows |
| Secrets and variables, Actions, Variables | `INTERFACE_REVIEWERS` = `GamitPrince,ArkinGamit,SHINE-18` |
| Code security | Secret scanning and push protection on; Dependabot alerts on; private vulnerability reporting on |

What `protect-main-develop` enforces on both `main` and `develop`:

| Your requirement | Ruleset setting |
| --- | --- |
| Protected `main` and `develop`, no direct push | Rule "Require a pull request before merging"; empty bypass list |
| Mandatory pull requests | Same rule |
| Independent review | 1 required approval; the author cannot approve their own PR; "Require approval of the most recent reviewable push"; stale approvals dismissed on new commits; conversations must be resolved |
| Green CI | Required checks `ci-gate`, `pr-policy`, `interfaces-review`; branch must be up to date |
| Squash-only | Allowed merge methods: squash; linear history required |
| 80% unit coverage | `ci-gate` includes each component's coverage check (see 8) |
| Safety approvals | CODEOWNERS: `firmware/src/safety/` and `docs/safety/` belong to the EE; "Require review from Code Owners" on |
| All three review `interfaces/` | CODEOWNERS plus the `interfaces-review` check |
| Story-first | `pr-policy` check (see 6) |
| No force push, no deleting `main` or `develop` | Rules "Restrict deletions" and "Block force pushes" |

## 6. What `pr-policy` checks on every pull request

1. Title is `type(scope): description`.
2. Branch is `feature|bugfix|hotfix/S-019-short-description` or `release/v0.1.0`. Only `release/*` and `hotfix/*` may target `main`.
3. The description contains `Closes #N`, and issue N is open, labelled story, bug or chore, and titled `S-019: ...` with the same ID as the branch.
4. All seven template checklist items are ticked.
5. A change under `firmware/src/safety/` or `docs/safety/` carries the `safety` label.
6. A pull request into `main` updates `CHANGELOG.md`.
7. No `.env`, key, `.elf`, `.bin`, `node_modules` or similar files.
8. More than about 300 changed lines gives a warning only.

## 7. Verify it works (everyone, practice PRs)

Do these once; each must behave as stated.

| Try | Expected |
| --- | --- |
| `git push origin develop` with a local commit | Rejected: protected branch |
| Open a PR with a title like "update stuff" | `pr-policy` fails with the reason |
| Open a PR without `Closes #N`, or from a branch like `my-fix` | `pr-policy` fails |
| Approve your own PR | GitHub does not allow it; merge stays blocked |
| Merge with a failing check | Merge button disabled |
| Open the merge dropdown | Only "Squash and merge" |
| Change a file in `firmware/src/safety/` | Needs the `safety` label and the EE's approval |
| Change a file in `interfaces/`; two developers approve | `interfaces-review` stays red until the third approves (the author counts as one) |
| Merge a PR | The branch is deleted and the story issue closes |

The first PR that runs the workflows also makes the check names appear in the PR; if a required check shows "Expected" and never starts, open the Actions tab and read the workflow error.

## 8. How the 80% coverage gate works

Each component runs `<component>/ci.sh` and must write `<component>/coverage.xml` in Cobertura format; `scripts/check_coverage.py` fails below 80% line coverage. Until a component has code, it passes. As soon as it has code without `ci.sh`, it fails. The tools that write Cobertura XML are chosen in the tech-stack ADRs (story P1-00); `pytest --cov --cov-report=xml`, `gcovr --cobertura` and `c8 report --reporter=cobertura` are examples. The Guide calls 80% a "target"; this setup makes it a hard gate, which is the stricter reading.

## 9. Project board and stories (PM)

1. Projects, New project (Board), name "Tank-AI". Status column options: Backlog, Ready, In Progress, Review, Blocked, Done.
2. Project settings, Workflows: auto-add new issues; set Status to Done when an issue is closed.
3. Create one issue per story card from the story-card template, title `S-0xx: ...`, with the component, priority and `must|should|could` labels and the sprint milestone. Create the first one for P1-00.

## 10. Emergency override

The bypass list is empty, so nobody can merge around the rules by accident. If something truly blocks a release, the owner can set a ruleset to Disabled (Settings, Rules, Rulesets), make the change, and set it back to Active the same hour. Write down who did it and why in the pull request. The owner can always change settings; this is a team-trust control, not protection against the owner.

## Known limits

- A **personal account has no teams**, so CODEOWNERS lists individual usernames and the "all three developers" rule needs the `interfaces-review` check. A free GitHub Organization would allow teams and shared ownership, at no cost.
- **GamitPrince is the only firmware and gateway developer**, so every firmware and gateway pull request is reviewed by ArkinGamit or SHINE-18. Pick the reviewer for the code, and for `firmware/src/safety/` the EE reviews as well. This keeps the rule "nobody approves their own PR", but a reviewer from the dashboard side may know less about firmware.
- **Nobody else can approve for the EE.** `gamitriyan-del` is the only owner of `firmware/src/safety/` and `docs/safety/`. If the EE writes a change in those folders, no one else can approve it, so add a second owner first.
- The branch-name rule applies to pull requests, not to pushing an oddly named branch.
- A squash merge of a `release/*` branch into `main` leaves `main` and `develop` with different history. The Guide's "merge back to `develop`" step may show conflicts; if it does, resolve them in the merge-back PR.
- The EE cannot approve a pull request they authored in `firmware/src/safety/`; another EE or the PM would need to be added as an owner.
- Milestones: the Guide mentions Sprint 0 to 6; the Phase 1 plan has four sprints, so the script creates Sprint 1 to 4.
