"""Finding the shared ``interfaces/`` contract folder.

Everything the simulator knows about signals and records comes from
``interfaces/`` (ADR-0004 decisions 6 and 9). The simulator does not keep a
copy: if the YAML and the code disagree, that is the bug this design exists to
prevent, so the files are read at runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable that overrides the search, for a consumer that vendors
#: the contract files somewhere else (a container image, for example).
ENV_VAR = "TANKSIM_INTERFACES_DIR"

#: Files that must all be present for a folder to be the contract folder.
REQUIRED_FILES = ("signals-v1.yaml", "records.cddl")


class InterfacesNotFound(RuntimeError):
    """Raised when the ``interfaces/`` folder cannot be located."""


def _is_interfaces_dir(candidate: Path) -> bool:
    return all((candidate / name).is_file() for name in REQUIRED_FILES)


def find_interfaces_dir(start: Path | None = None) -> Path:
    """Return the repository's ``interfaces/`` folder.

    ``TANKSIM_INTERFACES_DIR`` wins if it is set. Otherwise the search walks up
    from this module towards the filesystem root, which finds the folder both
    for an editable install inside the repository and for a checkout opened
    anywhere on disk.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        candidate = Path(override)
        if not _is_interfaces_dir(candidate):
            raise InterfacesNotFound(
                f"{ENV_VAR} is set to {candidate}, which does not contain "
                f"{' and '.join(REQUIRED_FILES)}"
            )
        return candidate

    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        candidate = parent / "interfaces"
        if _is_interfaces_dir(candidate):
            return candidate
    raise InterfacesNotFound(
        f"No interfaces/ folder containing {' and '.join(REQUIRED_FILES)} was found "
        f"above {here}. Set {ENV_VAR} to point at it."
    )


def signal_list_path(interfaces_dir: Path | None = None, version: int = 1) -> Path:
    """Path of the versioned signal list.

    The version is part of the filename on purpose: a device pinned to v1 gets a
    path that never changes meaning (``interfaces/README.md``).
    """
    base = interfaces_dir or find_interfaces_dir()
    return base / f"signals-v{version}.yaml"


def record_schema_path(interfaces_dir: Path | None = None) -> Path:
    """Path of the CBOR record schema."""
    base = interfaces_dir or find_interfaces_dir()
    return base / "records.cddl"
