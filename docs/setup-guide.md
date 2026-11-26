# Developer setup guide

How to get a Windows machine from nothing to a green local CI run for every component that has code today: the simulator, the FRDM firmware and the ESP32 logic. It covers the development system only. Bringing up the cloud, the dashboard and the bench rig comes later, in the runbook (P1-24's second part), when those exist.

Written for Windows 10 or 11 with PowerShell, VS Code and Git, the team's set-up (AGENTS.md section 3). CI itself runs the same scripts on Ubuntu.

## 1. Tools

| Tool | Why | Notes |
| --- | --- | --- |
| Git for Windows (with Git Bash) | Clone, and run the `.sh` scripts | `.gitattributes` keeps every text file LF, whatever `core.autocrlf` says |
| GitHub CLI (`gh`) | Issues and pull requests | Installs to `%LOCALAPPDATA%\Programs\GitHubCLI\bin` |
| Python 3.12 on Windows | The simulator | `py -3` works where `python3` is the Microsoft Store stub |
| WSL2 with Ubuntu | The Zephyr firmware build (ADR-0003) | Zephyr does not build natively on Windows here |

Set your Git identity before the first commit: `git config user.name` and `git config user.email`, your GitHub login and email.

## 2. Clone

```powershell
git clone https://github.com/GamitPrince/tank-controller.git
cd tank-controller
git switch develop
```

Every change starts from `develop` on a `feature|bugfix|hotfix/S-0xx-...` branch; see [CONTRIBUTING.md](../CONTRIBUTING.md).

## 3. Simulator (Windows, Git Bash)

```bash
PYTHON="$LOCALAPPDATA/Programs/Python/Python312/python.exe" bash scripts/ci/run-component.sh simulator
```

`PYTHON` must name one program, so give the full path to your `python.exe` (the folder name follows the version you installed), or `PYTHON=python` if `python` on your PATH is a real interpreter and not the Store stub. The script makes `simulator/.venv`, runs ruff and pytest, writes `simulator/coverage.xml` and fails under 80% line coverage. To run the simulator itself, see [simulator/README.md](../simulator/README.md): `python -m tanksim` from inside the venv runs ten scans with no hardware.

## 4. FRDM firmware (WSL2)

The firmware CI fetches Zephyr 4.5.0 with `west` into the repository root (`zephyr/`, `modules/`, `.west/`, all git-ignored), then builds and runs every ztest suite on `native_sim` with Twister and writes `firmware/coverage.xml`. A full run takes about 3 to 11 minutes.

**Two traps found on 25 Nov 2026:**

1. **A space in the checkout path breaks the Zephyr build.** A checkout under `C:\Users\<name with a space>\...` fails even through WSL's `/mnt/c/...`, and a symlink does not help. Clone inside the WSL file system (for example `~/tank-controller`), or copy your Windows checkout there with `rsync` before each run and never edit the copy.
2. **Ubuntu 22.04's own Python 3.10 and CMake 3.22 are too old** for Twister and Zephyr 4.5. Install Python 3.12 (for example from the deadsnakes PPA) and let the firmware venv carry a newer CMake: `pip install "cmake>=3.28,<4" clang-format` inside `firmware/.venv`. Ubuntu 24.04 ships new enough versions.

Zephyr's host build also needs a C compiler, Ninja and the device-tree compiler. On Ubuntu: `sudo apt install build-essential ninja-build device-tree-compiler python3.12-venv` (installs system-wide, so say so before you do it on a shared machine).

Then, from the repository root inside WSL:

```bash
PYTHON=python3.12 bash scripts/ci/run-component.sh firmware
```

`clang-format` is checked if it is on `PATH`; cppcheck runs only if installed and is advisory (AGENTS.md section 10). Format your own files before pushing:

```bash
firmware/.venv/bin/clang-format -i path/to/file.c
```

## 5. ESP32 logic (WSL2)

```bash
bash scripts/ci/run-component.sh esp32
```

It fetches Unity v2.6.1 into `esp32/build/`, builds the host tests with CMake, checks formatting against `firmware/.clang-format` and writes `esp32/coverage.xml`. ESP-IDF is not needed: ADR-0006 tests the logic as plain C on the host. Run it from the same WSL checkout as the firmware so CMake and clang-format are found.

## 6. Before you open a pull request

- All three component runs above are green locally for the folders you touched.
- The title is `type(scope): description`. The scope is one of `firmware gateway dashboard simulator hardware interfaces docs`; ESP32 work uses `firmware`.
- The body says `Closes #N` for the story issue, and every checklist item is ticked honestly.

## 7. Second-person check

P1-24's acceptance asks for a developer who did not write this guide to follow it from a clean machine. Until that has happened, treat any step here as unverified on a machine other than the tech lead's. Record the result in the P1-24 story when it is done.
