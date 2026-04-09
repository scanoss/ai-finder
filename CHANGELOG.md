# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Anonymous telemetry** for product improvement (enabled by default)
  - Tracks command usage, success/failure, duration, and error diagnostics
  - No file paths, scan targets, or PII collected
  - Opt-out via `--no-telemetry` flag, `SCANOSS_AI_TELEMETRY=0`, `DO_NOT_TRACK=1`, or config file
  - Config file location: `~/.scanoss-ai/config.json` with `{"telemetry": false}`

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [1.0.0] - YYYY-MM-DD

### Added
- Initial release
- Core functionality
- Documentation
- Tests

[Unreleased]: https://github.com/semclone/[project-name]/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/semclone/[project-name]/releases/tag/v1.0.0
