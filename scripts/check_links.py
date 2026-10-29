#!/usr/bin/env python3
"""Check that relative links in Markdown files point at files that exist."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", ".venv"}
FENCE = re.compile(r"```.*?```", re.DOTALL)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def main():
    broken = []
    for md in ROOT.rglob("*.md"):
        if SKIP_DIRS & set(md.relative_to(ROOT).parts):
            continue
        text = FENCE.sub("", md.read_text(encoding="utf-8"))
        for target in LINK.findall(text):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = target.split("#", 1)[0]
            if not path:
                continue
            base = ROOT if path.startswith("/") else md.parent
            if not (base / path.lstrip("/")).exists():
                broken.append(f"{md.relative_to(ROOT)}: {target}")
    if broken:
        print("Broken links:\n  " + "\n  ".join(broken))
        return 1
    print("All relative Markdown links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
