#!/usr/bin/env python3
"""Single source of truth for the QueryWeaver version.

`queryweaver/__init__.py` (`__version__`) is the ONE place the version is
authored. PyPI (dynamic build metadata) and the running UI (`GET /version`)
derive from it automatically. A few static manifests must embed a literal copy
of the version; this script keeps them in lock-step with the source and lets CI
fail on any drift.

Usage:
    python3 scripts/version.py current        # print the source version
    python3 scripts/version.py check          # verify all manifests match (exit 1 on drift)
    python3 scripts/version.py set X.Y.Z      # write the version into source + manifests
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The single source of truth.
SOURCE = ROOT / "queryweaver" / "__init__.py"
_VERSION_RE = re.compile(r"""(__version__\s*=\s*["'])([^"']+)(["'])""")

# Static manifests that must embed a literal copy of the source version.
PACKAGE_JSON = ROOT / "app" / "package.json"      # frontend bundle version
SERVER_JSON = ROOT / "server.json"                # MCP registry manifest (+ Docker image ref)

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-.]?(?:a|b|rc)[0-9]+)?$")


def read_source() -> str:
    """Return the authored version from queryweaver/__init__.py."""
    match = _VERSION_RE.search(SOURCE.read_text())
    if not match:
        sys.exit(f"error: could not find __version__ in {SOURCE}")
    return match.group(2)


def _manifest_versions() -> dict[str, list[tuple[str, str]]]:
    """Return {label: [(where, version), ...]} for every manifest literal."""
    pkg = json.loads(PACKAGE_JSON.read_text())
    server = json.loads(SERVER_JSON.read_text())
    return {
        "app/package.json": [("version", pkg.get("version", ""))],
        "server.json": [
            ("version", server.get("version", "")),
            *[
                (f"packages[{i}].version", p.get("version", ""))
                for i, p in enumerate(server.get("packages", []))
            ],
        ],
    }


def cmd_current() -> None:
    print(read_source())


def cmd_check() -> None:
    source = read_source()
    drift: list[str] = []
    for label, entries in _manifest_versions().items():
        for where, value in entries:
            if value != source:
                drift.append(f"  {label} [{where}] = {value!r} (expected {source!r})")
    if drift:
        print(f"Version drift detected. Source of truth is {source!r}:")
        print("\n".join(drift))
        print("\nFix with:  make release VERSION=" + source)
        sys.exit(1)
    print(f"All version manifests match the source: {source}")


def cmd_set(version: str) -> None:
    if not SEMVER_RE.match(version):
        sys.exit(f"error: {version!r} is not a valid SemVer version (e.g. 1.2.3)")

    # Source of truth.
    text, count = _VERSION_RE.subn(rf"\g<1>{version}\g<3>", SOURCE.read_text())
    if count != 1:
        sys.exit(f"error: expected exactly one __version__ in {SOURCE}, found {count}")
    SOURCE.write_text(text)

    # app/package.json — preserve key order and 2-space formatting.
    pkg = json.loads(PACKAGE_JSON.read_text())
    pkg["version"] = version
    PACKAGE_JSON.write_text(json.dumps(pkg, indent=2) + "\n")

    # server.json — top-level version and every published package version.
    server = json.loads(SERVER_JSON.read_text())
    server["version"] = version
    for pkg_entry in server.get("packages", []):
        pkg_entry["version"] = version
    SERVER_JSON.write_text(json.dumps(server, indent=2) + "\n")

    print(f"Set version to {version} in:")
    print(f"  {SOURCE.relative_to(ROOT)}")
    print(f"  {PACKAGE_JSON.relative_to(ROOT)}")
    print(f"  {SERVER_JSON.relative_to(ROOT)}")


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    cmd, *rest = argv
    if cmd == "current":
        cmd_current()
    elif cmd == "check":
        cmd_check()
    elif cmd == "set":
        if len(rest) != 1:
            sys.exit("usage: python3 scripts/version.py set X.Y.Z")
        cmd_set(rest[0])
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
