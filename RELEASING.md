# Releasing QueryWeaver

QueryWeaver publishes the `queryweaver` SDK to
[PyPI](https://pypi.org/project/queryweaver/). Releases are cut from a GitHub
Release and published automatically via PyPI Trusted Publishing (OIDC) — no API
tokens are stored.

This project follows [Semantic Versioning](https://semver.org). The version is
**single-sourced** in `queryweaver/__init__.py` (`__version__`); `pyproject.toml`
reads it dynamically and the backend serves it at `GET /version`.

## One-time setup (already required before the first automated release)

These steps cannot be scripted — they need PyPI and GitHub admin rights.

1. **PyPI** → project `queryweaver` → *Manage → Publishing* → add a Trusted
   Publisher: owner `FalkorDB`, repository `QueryWeaver`, workflow
   `publish-pypi.yml`, environment name `pypi`.
2. **TestPyPI** → same, with environment name `testpypi`. (TestPyPI cannot create
   a brand-new project via trusted publishing, so the project may need one manual
   seed upload there first.)
3. **GitHub** → repo *Settings → Environments* → create `pypi` and `testpypi`.

Until these exist, the publish workflow fails at the `uv publish` step.

## Cutting a release

1. **Pick the version** per SemVer (`MAJOR.MINOR.PATCH`).
2. **Update the changelog** — move items from `[Unreleased]` into a new dated
   `[X.Y.Z]` section in `CHANGELOG.md` and refresh the compare links at the
   bottom.
3. **Bump the version** in both files (kept in sync by the helper below):
   ```bash
   make release VERSION=X.Y.Z
   ```
   This updates `queryweaver/__init__.py` and `app/package.json`, then prints the
   tag/commit commands to run.
4. **Commit and open a PR** into `staging` (then `main`) with the bump +
   changelog.
5. **Tag and push** once merged, using a `v`-prefixed tag that matches the
   version:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
6. **Create the GitHub Release** for tag `vX.Y.Z` (paste the changelog section as
   the notes). Publishing the Release triggers `publish-pypi.yml`:
   - `verify-version` refuses to continue unless the tag matches
     `__version__`;
   - publishes to **TestPyPI** as a dry-run gate;
   - then publishes to **PyPI**.
7. **Verify** the new version appears on
   [PyPI](https://pypi.org/project/queryweaver/) and that `GET /version` reports
   it.

## Notes

- The tag (minus its leading `v`) **must** equal `__version__`. The workflow's
  `verify-version` job enforces this, so a mismatched tag fails fast instead of
  shipping the wrong version.
- The published wheel is SDK-only; the server layer is excluded (see
  `pyproject.toml` `[tool.hatch.build.targets.wheel]`).
- A version can only be published to (Test)PyPI once. If the PyPI step fails
  after TestPyPI succeeded, bump to the next patch rather than reusing the
  version.
