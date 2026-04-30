# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.3.2] - 2026-04-30

### Changed
- Consolidated the previously separate `ai-finder`, `ai-finder-kb`, and `ai-finder-scanner` distributions into a single `ai-finder` PyPI package. The Python module names (`ai_finder_cli`, `ai_finder_kb`, `ai_finder_scanner`) are unchanged, so existing imports continue to work.
- Release pipeline now publishes to TestPyPI on tag push; PyPI publish is a manual `workflow_dispatch` (`Promote to PyPI`) that pulls the artifacts from the GitHub Release.

### Removed
- Standalone binary builds for macOS, Linux, and Windows. The project now ships exclusively via PyPI (`pip install ai-finder`). Removed `.github/workflows/build-binaries.yml` and the `ai-finder.spec` PyInstaller config.

## [0.2.1] - 2026-04-08

### Changed
- Upgraded ptelemetry SDK to 0.2.0 for improved telemetry reliability

### Added
- **Anonymous telemetry** for product improvement (enabled by default)
  - Tracks command usage, success/failure, duration, and error diagnostics
  - Discrete events for funnel analysis (format, enrichment, findings, errors)
  - Granular error classification (file_not_found, network_error, etc.)
  - No file paths, scan targets, or PII collected
  - Opt-out via `--no-telemetry` flag, `AI_FINDER_TELEMETRY=0`, `DO_NOT_TRACK=1`, or config file
  - Config file location: `~/.ai-finder/config.json` with `{"telemetry": false}`
- Customer journey documentation (`docs/CUSTOMER_JOURNEY.md`) for funnel building
- Telemetry documentation (`docs/TELEMETRY.md`) explaining what is tracked and why

## [0.2.0] - 2026-04-08

### Added
- KB enrichment with live API fallback (HuggingFace, PyPI, npm)
- Component relationship graph with tree-sitter analysis
- SBOM dependency tracking (dependsOn/contains relationships)
- Data flow tracking for AI component outputs

## [1.0.0] - YYYY-MM-DD

### Added
- Initial release
- Core functionality
- Documentation
- Tests

[Unreleased]: https://github.com/scanoss/ai-finder/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/scanoss/ai-finder/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/scanoss/ai-finder/releases/tag/v0.2.0
