# CHORE-02: Rename `gitattributes` to `.gitattributes` and settle line endings

- Story ID: `[Confirm]` — not yet issued. This is a **repo chore**, not a Phase 1 feature story, so it has no `P1-xx` ID from the story card. The spec itself was delivered by S-021.
- Points: **2 (proposed)**. Priority: Should — not blocking, but it silently degrades every Windows checkout and it is cheap.
- Component: repo tooling. Review flag: none (does not touch `interfaces/` or a safety path).

## Goal

The repository's line-ending policy is committed as `gitattributes`, with no
leading dot, so **Git never reads it**. Rename it to `.gitattributes` so the
policy it already contains takes effect, and prove afterwards that it did.

## Phase check

Repository tooling only. No plant signal, no control path, no safety function,
no phase boundary. Nothing in `firmware/src/safety/` or `docs/safety/`.

## Measured facts

Every number below was measured on `develop` at `48679b6` on 21 Nov 2026, with
the command shown. **Do not inherit the older figures** — see "What the stale
note got wrong".

| Fact | Value | Command |
| --- | --- | --- |
| Tracked files | 122 | `git ls-files \| wc -l` |
| Tracked blobs containing a CR byte | **0 of 122** | per-blob `git cat-file blob "HEAD:$f" \| tr -dc '\r' \| wc -c` |
| Working-tree files with CRLF | **107 of 122** | per-file `tr -dc '\r' < "$f" \| wc -c` |
| Working-tree files already LF | 15 | same |
| `core.autocrlf` | **`true`**, from the **system** config | `git config --show-origin --get-all core.autocrlf` |
| `git check-attr text eol` on a tracked `.sh` | **both `unspecified`** | `git check-attr text eol -- firmware/ci.sh` |
| `.gitattributes` present | no | `ls -la .gitattributes` |
| Tracked binary files | none | `grep -II` over every tracked file; the ten `.gitkeep` hits are empty files, not binaries |

The CRLF working files break down as 47 `.md`, 31 `.py`, 7 `.yml`, **4 `.sh`**,
3 `.txt`, 2 `.yaml`, 2 `.json`, 2 `.c`, 1 each `.toml`, `.h`, `.cddl`, `.conf`,
`.clang-format`, `.example`, `.gitignore`, `.github/CODEOWNERS` — and
`gitattributes` itself.

## The two consequences that matter

**1. `git add --renormalize .` will produce nothing.** All 122 tracked blobs are
already pure LF. The index is clean; only the working tree is CRLF. So this
chore is a **one-file rename**, not a 23-file renormalisation commit. The
renormalise step still belongs in the plan below, as a *check* that must come
back empty rather than a step expected to produce a diff.

**2. The four shell scripts are the live hazard.** `firmware/ci.sh` (147 CR
bytes), `simulator/ci.sh` (69), `scripts/ci/run-component.sh` (37) and
`scripts/setup-github.sh` (103) are all CRLF in the working tree. They run
today, and a trivial CRLF script was confirmed to execute under Git Bash — but
CRLF is only *mostly* harmless in shell. It breaks `read` loops (the trailing
`\r` lands in the variable), heredoc terminators, `case` patterns, trailing
backslash continuations, and `export VAR=value` where the value gains a `\r`.
`firmware/ci.sh` and `run-component.sh` are exactly the kind of script that
uses those constructs, and the committed `gitattributes` comment names this
failure mode itself: "shell scripts fail with `\r: command not found`".

## What the stale note got wrong

`AGENTS.md` section 3 says `git status` "shows about 23 tracked files as
modified although only line endings differ", and `S-002-push-adrs.md` repeats
the figure. **That is not true on this repository now:**
`git diff --name-only | wc -l` returns **0**.

The reason is `core.autocrlf=true`, which masks the missing dot most of the
time. But the masking is **partial and inconsistent**, which was measured
rather than assumed while writing this spec:

- A **newly added** CRLF file is normalised: a probe file written with CRLF
  staged as a pure-LF blob (0 CR bytes).
- An **edit to an already-tracked file** was **not** normalised. Writing CRLF
  into `docs/stories/README.md` staged a blob with 95 CR bytes and a 94-line
  "every line changed" diff. It had to be converted to LF by hand before the
  real three-line diff appeared.

So a CRLF blob **can** be committed to this repository today, and it would
arrive disguised as a whole-file rewrite. That is a sharper reason to do this
chore than the noisy `git status` the stale note describes.

The setting also comes from the **system** config
(`C:/Program Files/Git/etc/gitconfig`), not from this repository, confirmed
with `git config --show-origin --get-all core.autocrlf`.

This matters for two reasons:

- **The masking is per-machine, not per-repository.** It comes from a Git
  installation's system config, so a fresh clone on a machine with
  `core.autocrlf` unset or set to `input` behaves differently. The repository
  currently depends on how each developer's Git happens to be installed, which
  is precisely what a committed `.gitattributes` exists to remove.
- **Git reads no line-ending policy at all right now.**
  `git check-attr text eol -- firmware/ci.sh` reports both as
  **`unspecified`**. That single command is the clearest proof the file is
  being ignored, and it is why it is acceptance criterion 2.
- **The ban on `git add -A` in AGENTS.md section 3 rests on a reason that no
  longer holds.** The ban should stay — PR #42 established a second and better
  reason, the west-fetched vendor directories — but the stated justification is
  out of date.

Whether `AGENTS.md` is corrected in this chore's PR or a separate
documentation story is **`[Confirm]`** for the tech lead. It is a tracked file,
so it cannot be edited in place without a story.

## The file as committed — do not rewrite it

```
# Store text files with LF line endings and check them out with LF on every system.
# Without this, Windows checkouts get CRLF and shell scripts fail with "\r: command not found".
* text=auto eol=lf
*.sh text eol=lf
*.py text eol=lf
*.yml text eol=lf
*.json text eol=lf
*.md text eol=lf
```

The content is correct and sufficient. `* text=auto eol=lf` already covers
every tracked extension, including the ones with no explicit line
(`.c`, `.h`, `.cddl`, `.conf`, `.toml`, `.yaml`, `.txt`, `.example`,
`.clang-format`, `CODEOWNERS`, `.gitignore`), which makes the five
per-extension lines redundant. **Leave them.** Tidying redundancy is not worth
widening a rename, and the explicit lines document intent for a reader.

Adding new rules, for example `*.bin binary` ahead of firmware artefacts, is
**out of scope**: nothing binary is tracked yet, and `.gitignore` already
excludes `.elf`/`.bin`.

## Files to create or change

- **Rename** `gitattributes` to `.gitattributes`. Content unchanged.
- `AGENTS.md` section 3, **only if** `[Confirm]` above says to do it here.
- `docs/stories/README.md`: move this chore out of "Backlog-level problems"
  item 4 and into the "Repo chores" table.
- `CHANGELOG.md` is **not** required: this PR targets `develop`, and
  `pr-policy` only requires a changelog entry for PRs into `main`.

## How to do it

1. Branch from `develop` as `bugfix/S-0xx-gitattributes-dot`. `pr-policy`
   accepts only `feature|bugfix|hotfix`, so there is **no `chore/` prefix** —
   CHORE-01's work story used `chore(scope)` in the *title*, not the branch.
2. `git mv gitattributes .gitattributes` — a plain rename, no content edit.
   Confirm with `git status` that Git records it as a rename and that the blob
   hash is unchanged.
3. Commit the rename **on its own**, so the rename is reviewable in isolation.
4. `git add --renormalize .` and then `git status`. **This must report nothing
   to commit.** If it reports files, a CRLF blob was committed after
   21 Nov 2026: stop, list them, and report before committing anything, because
   that turns a 1-file rename into a whole-tree commit that needs its own
   review.
5. Refresh the working tree so the new policy applies to it:
   `git rm --cached -r . -q && git reset --hard`. This rewrites 107 working
   files from CRLF to LF and **must not change the index**.
6. Re-verify: the working-tree CRLF count must be **0**, and
   `git diff --name-only` must still be empty.
7. Update `docs/stories/README.md`.

**Do not** use `git add -A`, `git commit -a`, `git stash` or `git reset`
without the explicit steps above, per AGENTS.md section 3. Step 5 uses
`reset --hard`, which is destructive: it must run only on a tree where
`git status` is clean apart from the intended rename, and the untracked files
in the repository root must be left alone.

## Risks

1. **`reset --hard` in step 5 discards uncommitted work.** The repository root
   currently holds several untracked `.md` files and the west-fetched
   directories. `reset --hard` leaves untracked files alone, but the step must
   still be run on an otherwise clean tree, and the operator must confirm
   `git status` first rather than trusting this spec.
2. **A rename to a dot-prefixed name on Windows.** `git mv` handles it; some
   Windows GUI tools and Explorer refuse to create a file whose name begins
   with a dot. Use `git mv`, not the file manager.
3. **The 107 working-file rewrite will look alarming in an editor.** Nothing is
   committed by it. Anyone with the repository open should expect every open
   buffer to report a change on disk.
4. **A second clone on another machine keeps CRLF until re-checked-out.** The
   fix applies on the next checkout of each file, not retroactively to an
   existing working tree. Say so in the PR so the EE and `prinz-assists` know
   to refresh rather than wonder why nothing changed.
5. **CI is unaffected and therefore proves nothing.** The runners are Ubuntu
   and check out LF either way. A green `ci-gate` is not evidence that this
   chore worked; the step 6 verification on a Windows tree is.

## Acceptance criteria

1. `.gitattributes` exists, tracked, with the content above byte-for-byte, and
   `gitattributes` no longer exists.
2. `git check-attr text eol -- firmware/ci.sh` reports `text: set` and
   `eol: lf`, proving Git now reads the file. **This is the criterion that
   actually tests the goal**; the rename alone does not.
3. `git add --renormalize .` reports nothing to commit, and the evidence is
   recorded in the PR.
4. After step 5, no tracked working-tree file contains a CR byte, measured and
   recorded, down from 107.
5. `git diff --name-only` is empty and no tracked blob's hash changed. The diff
   of the PR is a pure rename.
6. The four shell scripts still run: `bash scripts/ci/run-component.sh firmware`
   and `... simulator` pass in Git Bash after the change.
7. `ci-gate`, `pr-policy` and `interfaces-review` stay green, with no check
   edited, skipped or weakened.
8. `docs/stories/README.md` lists this chore as done rather than backlog-level.

## Test plan

Bench only; there is no simulator or hardware involvement.

- Before: record the CRLF count (107) and `git diff --name-only` (empty).
- After: re-run both and record them. Run `git check-attr` as in criterion 2.
- Run both `ci.sh` scripts through `run-component.sh` in Git Bash, and
  `firmware/ci.sh` in WSL2, to confirm the LF rewrite did not break the
  toolchain that CHORE-01 established.
- Paste the before and after numbers into the PR. **Do not** write "verified"
  without them: the whole reason this chore exists is that a stale number went
  unchecked for weeks.

## Dependency

None. Independent of every Phase 1 story and of PR #40 and PR #42. Best done
while no feature branch is open, because step 5 rewrites the working tree.

## Out of scope

- Adding or reordering any rule inside the file.
- `.editorconfig`, a pre-commit hook, or any other new line-ending mechanism.
- Changing `core.autocrlf` on a developer machine. The point of the fix is that
  the repository stops depending on it; a committed `.gitattributes` overrides
  it, and telling developers to change a global setting is the workaround this
  chore removes.
- The seven merged ADR status lines, and the fate of `gateway/`. Separate
  chores, both still unspecced.
- The `AGENTS.md` section 5 corrections listed in `docs/stories/README.md`.

## Open questions

- `[Confirm]` Correct the stale `AGENTS.md` section 3 sentence in this PR, or
  as its own documentation story? Doing it here keeps the fix and its
  documentation together; doing it separately keeps the PR a pure rename, which
  is easier to review and matches criterion 5.
- `[Confirm]` Story points — 2 proposed. Almost all of it is verification, not
  work.
- `[Confirm]` Should `prinz-assists` and the EE be asked to re-clone or
  re-check-out after this merges, given risk 4?
