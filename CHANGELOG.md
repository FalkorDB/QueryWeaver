# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `CHANGELOG.md` and `RELEASING.md` — documented, repeatable release process.
- Publish workflow now verifies the GitHub Release tag matches the
  single-sourced package version before publishing.

## [0.3.0] - Unreleased

Pending first automated release. See `RELEASING.md` for the cut process.

## [0.2.0] - 2026-06-24

Initial publish of the `queryweaver` SDK to [PyPI](https://pypi.org/project/queryweaver/).

### Added

- SDK-only PyPI package (`queryweaver`) exposing the `QueryWeaver` client and
  models; the server HTTP layer is excluded from the published wheel.
- Single-sourced version in `queryweaver/__init__.py`, surfaced at runtime via
  the public `GET /version` endpoint and shown in the app footer.

[Unreleased]: https://github.com/FalkorDB/QueryWeaver/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/FalkorDB/QueryWeaver/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/FalkorDB/QueryWeaver/releases/tag/v0.2.0
