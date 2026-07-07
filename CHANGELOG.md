# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.3.9] - 2026-07-07

### Fixed
- Semantic detectors were never run. The scanner wired only the per-language SDK detectors; `AgentDetector`, `ToolsDetector`, `RAGDetector`, and `DatasetDetector` were exported but never instantiated, so a project's agents, tools, embeddings, and datasets were never detected. They now run on every source file alongside the SDK detector.
- `@tool` false positive: the tool detector matched `@tool` anywhere on a line, so a docstring or comment mentioning `@tool` was reported as a tool. The decorator pattern is now anchored to the start of the (optionally indented) line.

### Added
- Strands agent detection: `from strands import Agent` / `strands.Agent` are recognized (joining langchain, crewai, autogen, and langgraph), without counting tool-only imports as agents.

## [0.3.8] - 2026-05-29

### Fixed
- `python-tlsh` moved from hard dependencies to the optional `[fuzzy]` extra. `osslili` treats TLSH as optional and degrades gracefully without it, so forcing the install was unnecessary. This unblocks Windows users who lack a C compiler (MSVC / Build Tools).

## [0.3.7] - 2026-05-06

### Added
- Seed entries for vector databases (ChromaDB, Pinecone, Weaviate, Qdrant, Milvus, FAISS, LanceDB), AI safety (Guardrails AI, NeMo Guardrails, LLM Guard, AIProxyGuard), speech/audio (OpenAI Whisper, Faster Whisper, ElevenLabs, Bark), observability (Tavily, LangSmith, W&B, MLflow, Accelerate, Datasets), and additional agent frameworks (Strands, CrewAI, AutoGen). SDK seed grows from 119 to 150.

### Fixed
- The package README on PyPI was a one-paragraph stub. Replaced with the full project description so the PyPI page matches the GitHub one.

## [0.3.6] - 2026-05-06

### Changed
- Expanded the bundled model seed from 5 to 706 entries.

## [0.3.5] - 2026-05-05

### Fixed
- Telemetry was disabled in the 0.3.4 wheel because the build-time substitution rewrote every occurrence of `__TELEMETRY_INGEST_KEY__` in `telemetry.py`, including the literal in the placeholder check that detects un-substituted source installs. The substitution is now line-anchored to the `_INGEST_KEY = "..."` assignment, and the workflow asserts post-substitution that the placeholder constant is intact.

## [0.3.4] - 2026-05-04

### Fixed
- Telemetry was silently a no-op for PyPI installs: the wheel build never substituted the `__TELEMETRY_INGEST_KEY__` placeholder (the substitution step lived in the deleted `build-binaries.yml`), and `ptelemetry` was not declared as a runtime dependency. The release pipeline now substitutes the placeholder before building the wheel, and `ptelemetry>=0.2.2` is a runtime dep. Tests added for every documented opt-out path.

## [0.3.3] - 2026-05-04

### Fixed
- Telemetry events were being sent to the `ptelemetry` SDK's default endpoint (`producttelemetry.com`) instead of `telemetry.scanoss.com`. The client now passes `api_url` explicitly.

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
