"""Dependabot majors held back for a reason must be released once the reason goes.

Two majors are pinned down in ``.github/dependabot.yml``:

* ``openai`` 3, because litellm requires ``openai<3.0.0`` and the only litellm
  that permits openai 3 is 1.83.0, which carries two critical advisories.
* ``typescript`` 7, because typescript-eslint's peer range stops below 6.1 and
  the app tsconfigs still set ``baseUrl``, which TS 7 removed. Either one alone
  keeps the hold alive.

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
APP_DIR = REPO_ROOT / "app"
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
        # `or []` rather than a default, because these keys can be present *and*
        # empty. Deleting the last entry but leaving `ignore:` behind is exactly
        # how a hold gets dropped, and YAML reads that as None - which must mean
        # "nothing held", not raise TypeError out of the guard.
        for update in entries
        for ignored in (update.get("ignore") or [])
        if MAJOR_UPDATE in (ignored.get("update-types") or [])
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ignore_block", "expected"),
    [
        (
            '    ignore:\n'
            '      - dependency-name: "typescript"\n'
            '        update-types: ["version-update:semver-major"]\n',
            {"typescript"},
        ),
        ("    ignore:\n", set()),
        ("", set()),
        (
            '    ignore:\n      - dependency-name: "typescript"\n        update-types:\n',
            set(),
        ),
    ],
    ids=["held", "ignore-key-left-empty", "no-ignore-key", "update-types-left-empty"],
)
def test_reading_holds_survives_a_half_deleted_ignore_block(
    ignore_block, expected, tmp_path, monkeypatch
):
    """Emptying a key without removing it is how a hold gets dropped by hand.

    YAML reads a present-but-empty key as None, and iterating that raises
    TypeError - which would replace this guard's explanatory failure with a
    stack trace at exactly the moment someone is editing the hold.
    """
    config = tmp_path / "dependabot.yml"
    config.write_text(
        'version: 2\nupdates:\n  - package-ecosystem: "npm"\n    directory: "/app"\n' + ignore_block,
        encoding="utf-8",
    )
    monkeypatch.setattr("tests.test_dependency_holds.DEPENDABOT_CONFIG", config)
    assert _major_holds("npm", "/app") == expected


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
    litellm_allows_openai_3 = specifier.contains(Version("3.0.0"))
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
    """Smallest major the range rules out entirely, or None when unbounded above.

    Upper bounds get written several ways and the difference matters: ``<7``,
    ``<7.0`` and ``<7.0.0`` all rule out every 7.x, while ``<7.1`` and ``<=7.1``
    still admit 7.0, so the first major they exclude outright is 8.
    """
    for unsupported, description in (("||", "an alternation"), (" - ", "a hyphen range")):
        assert unsupported not in peer_range, (
            f"Peer range {peer_range!r} contains {description}, which this check cannot read - "
            "a branch admitting the next major would be invisible to it. Read the range and "
            "update the hold in .github/dependabot.yml by hand."
        )

    excluded = []
    for operator, major, tail in re.findall(r"(<=?)\s*v?(\d+)((?:\.\d+)*)", peer_range):
        # `<=` always leaves its own major partly allowed, and so does a `<`
        # bound with a non-zero minor or patch.
        admits_part_of_major = operator == "<=" or any(
            part != "0" for part in tail.split(".")[1:]
        )
        excluded.append(int(major) + 1 if admits_part_of_major else int(major))
    return min(excluded) if excluded else None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("peer_range", "expected"),
    [
        (">=4.8.4 <6.1.0", 7),  # the range in the lockfile today
        (">=4.8.4 <7.0.0", 7),
        (">=4.8.4 <7.0", 7),
        (">=4.8.4 <7", 7),  # no dot: still excludes all of 7.x
        (">=4.8.4 <=6.9.0", 7),  # <= leaves part of 6 allowed
        (">=4.8.4 <=7", 8),
        (">=4.8.4", None),  # genuinely unbounded above
        ("*", None),
    ],
)
def test_lowest_excluded_major_reads_every_upper_bound_spelling(peer_range, expected):
    """The hold hangs off this parse, so a range it misreads silently stops enforcing."""
    assert _lowest_excluded_major(peer_range) == expected


def _declared_major(version_range: str) -> int:
    match = re.search(r"(\d+)\.", version_range)
    assert match, f"Cannot read a major version out of {version_range!r}."
    return int(match.group(1))


def _tsconfigs_setting_base_url() -> list[str]:
    """App tsconfigs that still set ``baseUrl``, which TypeScript 7 removed (TS5101).

    These files are JSONC - they carry ``/* ... */`` comments - so they are
    scanned as text rather than parsed.
    """
    tsconfigs = sorted(APP_DIR.glob("tsconfig*.json"))
    assert tsconfigs, (
        f"No tsconfig*.json under {APP_DIR}. A baseUrl in those files is one of the two "
        "reasons for the typescript major hold in .github/dependabot.yml, so re-read the "
        "hold before trusting this test."
    )
    return [
        path.name
        for path in tsconfigs
        if re.search(r'^\s*"baseUrl"\s*:', path.read_text(encoding="utf-8"), re.MULTILINE)
    ]


@pytest.mark.unit
def test_typescript_major_is_held_exactly_while_anything_blocks_it():
    peer_range = _typescript_eslint_peer_range()
    declared = json.loads(APP_PACKAGE_JSON.read_text(encoding="utf-8"))
    next_major = _declared_major(declared["devDependencies"]["typescript"]) + 1

    excluded_from = _lowest_excluded_major(peer_range)
    base_url_configs = _tsconfigs_setting_base_url()

    blockers = []
    if excluded_from is not None and excluded_from <= next_major:
        blockers.append(
            f"typescript-eslint declares peer typescript {peer_range!r}, which excludes "
            f"{next_major}.x, so the bump breaks `npm install` with ERESOLVE"
        )
    if base_url_configs:
        blockers.append(
            f"{', '.join(base_url_configs)} still set baseUrl, which TypeScript 7 "
            "removed (TS5101)"
        )

    held = "typescript" in _major_holds("npm", "/app")

    if blockers:
        assert held, (
            f"typescript {next_major} is still blocked: "
            + "; ".join(blockers)
            + ". Restore the typescript major hold in .github/dependabot.yml instead of "
            "removing it."
        )
    else:
        assert not held, (
            f"Nothing blocks typescript {next_major} any more - typescript-eslint's peer "
            f"range {peer_range!r} admits it and no app tsconfig sets baseUrl - so the hold "
            "in .github/dependabot.yml is stale. Drop the typescript ignore block."
        )
