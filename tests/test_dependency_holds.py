"""Dependabot majors held back for a reason must be released once the reason goes.

Two majors are pinned down in ``.github/dependabot.yml``:

* ``openai`` 3, because litellm requires ``openai<3.0.0`` and the only litellm
  that permits openai 3 is 1.83.0, which carries two critical advisories.
* ``typescript`` 7, because typescript-eslint's peer range stops below 6.1.

An ``ignore`` entry is invisible: nothing fails when the upstream constraint is
finally relaxed, so the hold quietly turns into an unexplained pin and the
dependency rots. These tests read the reason from the same place the resolver
does - litellm's installed metadata and typescript-eslint's recorded peer
range - and fail in *both* directions: if the hold is dropped while the
constraint still stands, and if the constraint lifts while the hold remains.
"""

import json
import re
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

try:  # Python 3.12 always has this; guard keeps the import obvious.
    from importlib.metadata import requires as distribution_requires
except ImportError:  # pragma: no cover - unreachable on requires-python >=3.12
    distribution_requires = None

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"
APP_PACKAGE_JSON = REPO_ROOT / "app" / "package.json"
APP_PACKAGE_LOCK = REPO_ROOT / "app" / "package-lock.json"

MAJOR_UPDATE = "version-update:semver-major"


def _major_holds(ecosystem: str, directory: str) -> set[str]:
    """Names whose *major* updates ``.github/dependabot.yml`` ignores for one ecosystem."""
    config = yaml.safe_load(DEPENDABOT_CONFIG.read_text(encoding="utf-8"))
    entries = [
        update
        for update in config["updates"]
        if update["package-ecosystem"] == ecosystem and update["directory"] == directory
    ]
    assert entries, (
        f"No {ecosystem!r} update block for {directory!r} in .github/dependabot.yml. "
        "If the ecosystem was renamed or removed, move or delete the hold this test guards."
    )
    return {
        ignored["dependency-name"]
        for update in entries
        for ignored in update.get("ignore", [])
        if MAJOR_UPDATE in ignored.get("update-types", [])
    }


def _litellm_openai_specifier() -> SpecifierSet:
    """The openai range litellm itself declares, read from the installed distribution."""
    declared = distribution_requires("litellm") or []
    openai_requirements = [
        requirement
        for requirement in (Requirement(entry) for entry in declared)
        if requirement.name == "openai" and requirement.marker is None
    ]
    assert len(openai_requirements) == 1, (
        f"Expected exactly one unconditional openai requirement in litellm's metadata, "
        f"got {[str(r) for r in openai_requirements]}. The hold in .github/dependabot.yml "
        "is justified by that requirement, so re-read it before trusting this test."
    )
    return openai_requirements[0].specifier


@pytest.mark.unit
def test_openai_major_is_held_exactly_while_litellm_forbids_it():
    specifier = _litellm_openai_specifier()
    # prereleases=True so a 3.0.0rc release does not read as "still forbidden".
    litellm_allows_openai_3 = specifier.contains(Version("3.0.0"), prereleases=True)
    held = "openai" in _major_holds("uv", "/")

    if litellm_allows_openai_3:
        assert not held, (
            f"litellm now permits openai 3 ({specifier}), so the hold in .github/dependabot.yml "
            "is stale - drop the openai ignore block and let the major through."
        )
    else:
        assert held, (
            f"litellm still requires {specifier}, so resolving openai 3 falls back to litellm "
            "1.83.0 (two critical advisories). Restore the openai major hold in "
            ".github/dependabot.yml instead of removing it."
        )


def _typescript_eslint_peer_range() -> str:
    """typescript-eslint's declared peer range on typescript, from the committed lockfile."""
    lockfile = json.loads(APP_PACKAGE_LOCK.read_text(encoding="utf-8"))
    entries = [
        package
        for name, package in lockfile["packages"].items()
        if name.split("node_modules/")[-1] == "typescript-eslint"
    ]
    assert len(entries) == 1, (
        f"Expected exactly one typescript-eslint entry in app/package-lock.json, found {len(entries)}. "
        "The typescript hold is justified by its peer range, so re-read it before trusting this test."
    )
    peer_range = entries[0].get("peerDependencies", {}).get("typescript")
    assert peer_range, (
        "typescript-eslint no longer declares a peer dependency on typescript. That removes the "
        "reason for the typescript major hold in .github/dependabot.yml - re-check it."
    )
    return peer_range


def _lowest_excluded_major(peer_range: str) -> int | None:
    """Smallest major the range rules out via a ``<`` bound, or None when unbounded above."""
    bounds = re.findall(r"<\s*=?\s*(\d+)\.", peer_range)
    return min(int(bound) for bound in bounds) if bounds else None


def _declared_major(version_range: str) -> int:
    match = re.search(r"(\d+)\.", version_range)
    assert match, f"Cannot read a major version out of {version_range!r}."
    return int(match.group(1))


@pytest.mark.unit
def test_typescript_major_is_held_exactly_while_typescript_eslint_rejects_it():
    peer_range = _typescript_eslint_peer_range()
    declared = json.loads(APP_PACKAGE_JSON.read_text(encoding="utf-8"))
    next_major = _declared_major(declared["devDependencies"]["typescript"]) + 1

    excluded_from = _lowest_excluded_major(peer_range)
    peer_rejects_next_major = excluded_from is not None and excluded_from <= next_major
    held = "typescript" in _major_holds("npm", "/app")

    if peer_rejects_next_major:
        assert held, (
            f"typescript-eslint still declares peer typescript {peer_range!r}, which excludes "
            f"{next_major}.x, so the bump breaks `npm install` with ERESOLVE. Restore the typescript "
            "major hold in .github/dependabot.yml instead of removing it."
        )
    else:
        assert not held, (
            f"typescript-eslint now declares peer typescript {peer_range!r}, which admits "
            f"{next_major}.x, so the hold in .github/dependabot.yml is stale. Drop the typescript "
            "ignore block and migrate (tsconfig.app.json still uses baseUrl, removed in TS 7)."
        )
