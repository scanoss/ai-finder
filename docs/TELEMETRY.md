# Telemetry

ai-finder collects anonymous usage data to help improve the tool. This document describes what data is collected, why we collect it, how to opt out, and our privacy commitments.

## Why We Track

Telemetry helps us understand how ai-finder is used in the real world so we can make better decisions about product development.

### What We Learn

| Question | How Telemetry Helps |
|----------|---------------------|
| **Which output formats are most used?** | We track `scan.format.cyclonedx` vs `scan.format.spdx` to prioritize SBOM format improvements |
| **Is KB enrichment valuable?** | We track `scan.enrich.enabled` and `identify.kb_match.found` to understand adoption and success rates |
| **What errors do users hit?** | We track `error.scan.file_not_found` and `error.identify.parse_error` to fix common issues |
| **How large are typical scans?** | We track `findings_count` buckets to optimize performance for real-world usage |
| **Is the KB crawling working?** | We track `kb.crawl.*.result.success` vs `kb.crawl.*.errors.yes` to monitor data quality |

### How This Improves the Product

1. **Prioritize features** - If most users use CycloneDX, we focus on CycloneDX improvements
2. **Fix real issues** - Error tracking shows us what actually breaks in production
3. **Optimize performance** - Understanding typical scan sizes helps us optimize the right code paths
4. **Validate changes** - After a release, we can see if error rates decrease
5. **Guide documentation** - If users hit the same errors repeatedly, we improve docs

### What We Don't Do

- We don't track individual users or sessions
- We don't correlate events to identify user behavior patterns
- We don't sell or share telemetry data with third parties
- We don't use telemetry for advertising or marketing

## Privacy Commitments

**We never collect:**
- File paths or scan targets
- PURL values or package names you look up
- Model file names, hashes, or contents
- Stack traces or error messages (which could contain paths)
- Any personally identifiable information (PII)

**We only collect:**
- Which commands are run and their options (format, flags)
- Success/failure status and duration
- Aggregate counts (files scanned, findings count)
- Exception type names (e.g., `FileNotFoundError`, not the message)

## Opt-Out

Disable telemetry using any of these methods:

### CLI Flag (per-session)

```bash
ai-finder --no-telemetry scan /path/to/project
```

### Environment Variables

```bash
# AI Finder-specific
export AI_FINDER_TELEMETRY=0

# Universal opt-out standard (https://consoledonottrack.com/)
export DO_NOT_TRACK=1
```

### Config File (persistent)

Create `~/.ai-finder/config.json`:

```json
{
  "telemetry": false
}
```

## Events Collected

All events are designed for **funnel analysis** - each behavior emits a discrete event that can be counted and visualized as funnel steps.

### Lifecycle Events

| Event | Description |
|-------|-------------|
| `cli.started` | CLI was invoked |

### Command Events (with properties)

Each command emits `started` and `completed` events with properties for detailed analysis:

| Command | Started Properties | Completed Properties |
|---------|-------------------|---------------------|
| scan | `format`, `quiet`, `enrich`, `relationships` | `files_scanned`, `findings_count`, `output_format`, `model_count`, `sdk_count`, `manifest_count`, `kb_available`, `graph_nodes`, `graph_edges` |
| identify | `format`, `enrich` | `recognized`, `kb_match`, `output_format`, `model_format`, `kb_available` |
| kb.init | - | - |
| kb.status | `format` | `schema_version`, `total_entries`, `output_format` |
| kb.lookup | `format` | `results_count` |
| kb.crawl | `source` | `items_added`, `error_count` |

### Discrete Feature Events (for funnels)

These events enable funnel visualization without parsing properties:

#### scan

##### Scan Pipeline Events (ordered funnel)

| Event | Description |
|-------|-------------|
| `scan.started` | Scan execution started |
| `scan.discovery.started` | File discovery phase started |
| `scan.discovery.completed` | File discovery completed (with file counts) |
| `scan.detection.started` | Detection phase started (sdk/manifest/model) |
| `scan.detection.completed` | Detection phase completed (with finding counts) |
| `scan.sdk.found` | Individual SDK detected (per SDK) |
| `scan.manifest_dep.found` | Individual manifest dependency found (per dep) |
| `scan.metrics` | Overall scan metrics |
| `scan.completed` | Scan execution completed successfully |
| `scan.enrichment.started` | KB enrichment phase started |
| `scan.enrichment.completed` | KB enrichment phase completed |
| `scan.output.started` | SBOM output generation started |
| `scan.output.completed` | SBOM output generation completed |

##### Scan Feature Events

| Event | Description |
|-------|-------------|
| `scan.format.json` | Output format is JSON |
| `scan.format.cyclonedx` | Output format is CycloneDX SBOM |
| `scan.format.spdx` | Output format is SPDX SBOM |
| `scan.format.text` | Output format is text |
| `scan.enrich.enabled` | KB enrichment is enabled |
| `scan.relationships.enabled` | Relationship graph is enabled |
| `scan.findings.none` | No AI artifacts found |
| `scan.findings.few` | 1-10 AI artifacts found |
| `scan.findings.many` | 10+ AI artifacts found |
| `scan.artifact_type.model` | Model files found |
| `scan.artifact_type.sdk` | SDK usage found |
| `scan.artifact_type.manifest` | Manifest dependencies found |
| `scan.graph_built.success` | Relationship graph built |
| `scan.kb_source.local` | Using local KB cache |
| `scan.kb_source.live_only` | No local KB, using live APIs |

##### Complete Scan Funnel

```
cli.started
 -> command.scan.started
    -> scan.started
       -> scan.discovery.started
       -> scan.discovery.completed
       -> scan.detection.started (phase: sdk)
       -> scan.sdk.found (per SDK)
       -> scan.detection.completed (phase: sdk)
       -> scan.detection.started (phase: manifest)
       -> scan.manifest_dep.found (per dependency)
       -> scan.detection.completed (phase: manifest)
       -> scan.detection.started (phase: model)
       -> scan.detection.completed (phase: model)
       -> scan.metrics
       -> scan.completed
    -> scan.enrichment.started
       -> enrichment.* events
    -> scan.enrichment.completed
    -> scan.output.started
    -> scan.output.completed
 -> command.scan.completed
```

#### identify

| Event | Description |
|-------|-------------|
| `identify.format.json` | Output format is JSON |
| `identify.format.text` | Output format is text |
| `identify.enrich.enabled` | KB enrichment is enabled |
| `identify.unknown_extension.{ext}` | Unknown file extension encountered |
| `identify.recognized.yes` | Model file was recognized |
| `identify.recognized.no` | Model file was not recognized |
| `identify.model_format.gguf` | Model format is GGUF |
| `identify.model_format.safetensors` | Model format is SafeTensors |
| `identify.model_format.onnx` | Model format is ONNX |
| `identify.model_format.pytorch` | Model format is PyTorch |
| `identify.kb_source.local` | Using local KB cache |
| `identify.kb_source.live_only` | No local KB, using live APIs |
| `identify.kb_match.found` | KB lookup found a match |
| `identify.kb_match.not_found` | KB lookup found no match |

#### kb.status

| Event | Description |
|-------|-------------|
| `kb.status.format.json` | Output format is JSON |
| `kb.status.format.text` | Output format is text |
| `kb.status.db.not_found` | KB database doesn't exist |
| `kb.status.entries.empty` | KB has 0 entries |
| `kb.status.entries.small` | KB has 1-99 entries |
| `kb.status.entries.medium` | KB has 100-999 entries |
| `kb.status.entries.large` | KB has 1000+ entries |

#### kb.lookup

| Event | Description |
|-------|-------------|
| `kb.lookup.format.json` | Output format is JSON |
| `kb.lookup.format.text` | Output format is text |
| `kb.lookup.result.found` | Lookup found results |
| `kb.lookup.result.not_found` | Lookup found no results |
| `kb.lookup.found_type.sdk` | Found SDK entries |
| `kb.lookup.found_type.model` | Found model entries |
| `kb.lookup.found_type.package` | Found package entries |

#### kb.crawl

| Event | Description |
|-------|-------------|
| `kb.crawl.source.huggingface` | Crawling HuggingFace |
| `kb.crawl.source.pypi` | Crawling PyPI |
| `kb.crawl.source.npm` | Crawling npm |
| `kb.crawl.source.all` | Crawling all sources |
| `kb.crawl.crawler.huggingface` | HuggingFace crawler ran |
| `kb.crawl.crawler.pypi` | PyPI crawler ran |
| `kb.crawl.crawler.npm` | npm crawler ran |
| `kb.crawl.db_init.created` | KB was auto-initialized |
| `kb.crawl.huggingface.result.success` | HuggingFace added items |
| `kb.crawl.pypi.result.success` | PyPI added items |
| `kb.crawl.npm.result.success` | npm added items |
| `kb.crawl.huggingface.errors.yes` | HuggingFace had errors |
| `kb.crawl.pypi.errors.yes` | PyPI had errors |
| `kb.crawl.npm.errors.yes` | npm had errors |
| `kb.crawl.result.success` | Overall crawl added items |
| `kb.crawl.result.empty` | Overall crawl added nothing |
| `kb.crawl.had_errors.yes` | Overall crawl had errors |

#### Enrichment Events (from KBEnricher)

These events are emitted during KB enrichment in scan and identify commands:

| Event | Properties | Description |
|-------|------------|-------------|
| `enrichment.cache_hit` | `type` | Session cache hit (avoids repeated lookups) |
| `enrichment.kb_hit` | `type`, `name`/`ecosystem` | Found in local KB cache |
| `enrichment.live_fetch` | `type`, `source` | Successfully fetched from live API |
| `enrichment.model_not_found` | `source`, `name` | Model not found in HuggingFace |
| `enrichment.package_not_found` | `source`, `name` | Package not found in PyPI/npm |
| `enrichment.live_fetch_failed` | `type`, `source`, `error_category` | Live API fetch failed |
| `enrichment.unsupported_ecosystem` | `ecosystem` | Unsupported package ecosystem |

**Enrichment error categories:**
- `network_error` - Connection failed
- `timeout` - Request timed out
- `ssl_error` - SSL/TLS error
- `not_found` - 404 response
- `rate_limited` - 429 response
- `auth_error` - 401/403 response
- `server_error` - 5xx response
- `http_error` - Other HTTP error
- `missing_dependency` - Required library not installed
- `parse_error` - JSON/response parsing failed
- `unknown` - Unclassified error

### Error Events (granular)

Errors emit discrete events for funnel analysis:

| Event Pattern | Description |
|---------------|-------------|
| `error.{command}.file_not_found` | File not found |
| `error.{command}.permission_denied` | Permission denied |
| `error.{command}.is_directory` | Expected file, got directory |
| `error.{command}.disk_full` | Disk full |
| `error.{command}.out_of_memory` | Out of memory |
| `error.{command}.symlink_loop` | Symlink loop detected |
| `error.{command}.os_error` | Other OS error |
| `error.{command}.invalid_value` | Invalid value |
| `error.{command}.network_error` | Network error |
| `error.{command}.http_error` | HTTP error |
| `error.{command}.database_error` | Database error |
| `error.{command}.parse_error` | Parse/decode error |
| `error.{command}.encoding_error` | Encoding error |
| `error.{command}.unknown` | Unknown error |

Plus a generic `error` event with properties for detailed analysis:
- `error_type`: Exception class name
- `error_category`: Classified category
- `context`: Command context

**Note:** Error messages and stack traces are never sent.

## Implementation

Telemetry is implemented in `packages/ai-finder/src/ai_finder_cli/telemetry.py`. Key design decisions:

1. **Fail-closed**: If the config file is unreadable or the telemetry library fails to initialize, telemetry is disabled.

2. **Lazy initialization**: The telemetry client is only created on first use, after checking all opt-out mechanisms.

3. **Graceful shutdown**: Events are flushed on CLI exit via `atexit`.

4. **No blocking**: Telemetry operations do not block CLI execution.

## Data Handling

- **Backend**: Events are sent to SCANOSS telemetry infrastructure
- **Retention**: Usage data is retained for product analytics purposes
- **Access**: Data is only accessible to SCANOSS engineering team

## Questions?

If you have questions about telemetry or privacy, please open an issue at https://github.com/scanoss/ai-finder/issues.
