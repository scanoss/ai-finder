# Customer Journey Map

This document maps the complete user journey through ai-finder, showing all entry points, decision paths, outcomes, and telemetry events for funnel analysis.

## Journey Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCANOSS-AI USER JOURNEYS                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐          │
│   │  SCAN    │     │ IDENTIFY │     │    KB    │     │  ERROR   │          │
│   │ Journey  │     │ Journey  │     │ Journey  │     │  Paths   │          │
│   └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘          │
│        │                │                │                │                 │
│        ▼                ▼                ▼                ▼                 │
│   [SBOM Gen]       [Model ID]       [KB Setup]      [Recovery]             │
│   [Compliance]     [Validation]     [Data Sync]     [Support]              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. SCAN Journey (Primary Use Case)

The main workflow for scanning codebases for AI artifacts.

### Entry Points

| Entry | User Goal | Typical User |
|-------|-----------|--------------|
| `ai-finder scan .` | Quick scan, text output | Developer exploring |
| `ai-finder scan . -f cyclonedx` | Generate SBOM for compliance | Security team |
| `ai-finder scan . -f spdx` | Generate SBOM (SPDX format) | Compliance officer |
| `ai-finder scan . -r` | Include relationships | Architect |
| `ai-finder scan . --no-enrich` | Fast scan, no API calls | CI/CD pipeline |

### Journey Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SCAN JOURNEY                                    │
└─────────────────────────────────────────────────────────────────────────────┘

ENTRY
  │
  ▼
cli.started ─────────────────────────────────────────────────────────────────┐
  │                                                                           │
  ▼                                                                           │
command.scan.started                                                          │
  │                                                                           │
  ├─► scan.format.{json|text|cyclonedx|spdx}                                 │
  │                                                                           │
  ├─► scan.enrich.enabled (if enrichment on)                                 │
  │                                                                           │
  └─► scan.relationships.enabled (if -r flag)                                │
      │                                                                       │
      ▼                                                                       │
┌─────────────────────────────────────────────────────────────────────────────┤
│ SCANNING PHASE                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [Discover Files] ──► [Parse Files] ──► [Detect Artifacts]                │
│                                                                             │
│   Outcomes:                                                                 │
│   ├─► scan.findings.none      (0 artifacts)      ──► EXIT: No AI found    │
│   ├─► scan.findings.few       (1-10 artifacts)   ──► Continue             │
│   └─► scan.findings.many      (10+ artifacts)    ──► Continue             │
│                                                                             │
│   Artifact Types Found:                                                     │
│   ├─► scan.artifact_type.model     (GGUF, SafeTensors, etc.)              │
│   ├─► scan.artifact_type.sdk       (OpenAI, Anthropic imports)            │
│   └─► scan.artifact_type.manifest  (requirements.txt deps)                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┤
      │                                                                       │
      ▼                                                                       │
┌─────────────────────────────────────────────────────────────────────────────┤
│ RELATIONSHIPS PHASE (if enabled)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [Build Graph] ──► [Analyze Dependencies]                                 │
│                                                                             │
│   Outcomes:                                                                 │
│   └─► scan.graph_built.success                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┤
      │                                                                       │
      ▼                                                                       │
┌─────────────────────────────────────────────────────────────────────────────┤
│ ENRICHMENT PHASE (if enabled)                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   KB Source:                                                                │
│   ├─► scan.kb_source.local      (has local KB)                             │
│   └─► scan.kb_source.live_only  (no local KB)                              │
│                                                                             │
│   For each artifact:                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                                                                     │  │
│   │  ┌─► enrichment.cache_hit (in session cache)                       │  │
│   │  │                                                                  │  │
│   │  └─► [Check KB] ─┬─► enrichment.kb_hit (found in local KB)        │  │
│   │                  │                                                  │  │
│   │                  └─► [Live API] ─┬─► enrichment.live_fetch         │  │
│   │                                  │                                  │  │
│   │                                  ├─► enrichment.model_not_found    │  │
│   │                                  ├─► enrichment.package_not_found  │  │
│   │                                  │                                  │  │
│   │                                  └─► enrichment.live_fetch_failed  │  │
│   │                                      ├─► network_error             │  │
│   │                                      ├─► timeout                   │  │
│   │                                      ├─► rate_limited              │  │
│   │                                      └─► server_error              │  │
│   │                                                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┤
      │                                                                       │
      ▼                                                                       │
┌─────────────────────────────────────────────────────────────────────────────┤
│ OUTPUT PHASE                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [Format Output] ──► [Write File / Stdout]                                │
│                                                                             │
│   Output:                                                                   │
│   ├─► JSON (machine readable)                                              │
│   ├─► CycloneDX SBOM (compliance)                                          │
│   ├─► SPDX SBOM (compliance)                                               │
│   └─► Text (human readable)                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┤
      │                                                                       │
      ▼                                                                       │
command.scan.completed ───────────────────────────────────────────────────────┤
  │                                                                           │
  ▼                                                                           │
EXIT                                                                          │
  ├─► Success (exit 0) ─► User has SBOM / findings                           │
  └─► Error (exit 1) ──► error.scan.{category}                               │
                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Scan Exit States

| Exit | Event | User Action |
|------|-------|-------------|
| Success - No findings | `scan.findings.none` | May run on different path |
| Success - Few findings | `scan.findings.few` | Review SBOM |
| Success - Many findings | `scan.findings.many` | Compliance review |
| Error - File not found | `error.scan.file_not_found` | Check path |
| Error - Permission denied | `error.scan.permission_denied` | Fix permissions |
| Error - Parse error | `error.scan.parse_error` | Report bug |

---

## 2. IDENTIFY Journey

Single file model identification workflow.

### Entry Points

| Entry | User Goal |
|-------|-----------|
| `ai-finder identify model.gguf` | Identify unknown model file |
| `ai-finder identify model.gguf -f json` | Get structured metadata |
| `ai-finder identify model.gguf --no-enrich` | Quick local-only check |

### Journey Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            IDENTIFY JOURNEY                                  │
└─────────────────────────────────────────────────────────────────────────────┘

ENTRY
  │
  ▼
cli.started
  │
  ▼
command.identify.started
  │
  ├─► identify.format.{json|text}
  └─► identify.enrich.enabled (if enrichment on)
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PARSING PHASE                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [Read File] ──► [Detect Format] ──► [Parse Metadata]                     │
│                                                                             │
│   Extension Check:                                                          │
│   └─► identify.unknown_extension.{ext} (if unknown)                        │
│                                                                             │
│   Recognition:                                                              │
│   ├─► identify.recognized.yes ─┬─► identify.model_format.gguf              │
│   │                            ├─► identify.model_format.safetensors       │
│   │                            ├─► identify.model_format.onnx              │
│   │                            └─► identify.model_format.pytorch           │
│   │                                                                         │
│   └─► identify.recognized.no ──► EXIT: Unknown format (exit 1)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ENRICHMENT PHASE (if enabled & recognized)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   KB Source:                                                                │
│   ├─► identify.kb_source.local                                             │
│   └─► identify.kb_source.live_only                                         │
│                                                                             │
│   Lookup:                                                                   │
│   ├─► identify.kb_match.found ──► Add license, org, source info           │
│   │       └─► enrichment.kb_hit / enrichment.live_fetch                    │
│   │                                                                         │
│   └─► identify.kb_match.not_found ──► Model not in KB                      │
│           └─► enrichment.model_not_found                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
command.identify.completed
  │
  ▼
EXIT
  ├─► Success - Recognized (exit 0)
  ├─► Not recognized (exit 1)
  └─► Error (exit 2) ─► error.identify.{category}
```

### Identify Exit States

| Exit Code | Meaning | Event |
|-----------|---------|-------|
| 0 | Model recognized | `identify.recognized.yes` |
| 1 | Model not recognized | `identify.recognized.no` |
| 2 | Error occurred | `error.identify.*` |

---

## 3. KB Journey

Knowledge Base setup and maintenance workflow.

### Entry Points

| Entry | User Goal |
|-------|-----------|
| `ai-finder kb init` | Initialize local KB |
| `ai-finder kb status` | Check KB state |
| `ai-finder kb crawl huggingface` | Populate with HuggingFace models |
| `ai-finder kb crawl all` | Full KB population |
| `ai-finder kb lookup pkg:huggingface/...` | Search KB |

### Journey Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              KB JOURNEY                                      │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │   KB COMMANDS   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    ┌─────────┐        ┌──────────┐        ┌──────────┐
    │  INIT   │        │  STATUS  │        │  CRAWL   │
    └────┬────┘        └────┬─────┘        └────┬─────┘
         │                  │                   │
         ▼                  ▼                   ▼
   [Create DB]      [Check DB State]     [Fetch Data]
         │                  │                   │
         │                  │                   │
         ▼                  ▼                   ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│ KB INIT                                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   command.kb.init.started                                                   │
│       │                                                                     │
│       ▼                                                                     │
│   [Create Directory] ──► [Initialize Schema]                               │
│       │                                                                     │
│       ▼                                                                     │
│   command.kb.init.completed                                                 │
│       │                                                                     │
│       ▼                                                                     │
│   EXIT: KB ready for crawl                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ KB STATUS                                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   command.kb.status.started                                                 │
│       │                                                                     │
│       ├─► kb.status.format.{json|text}                                     │
│       │                                                                     │
│       ├─► kb.status.db.not_found ──► EXIT: Need to init                    │
│       │                                                                     │
│       └─► [Read Stats]                                                     │
│               │                                                             │
│               ├─► kb.status.entries.empty   (0 entries)                    │
│               ├─► kb.status.entries.small   (1-99)                         │
│               ├─► kb.status.entries.medium  (100-999)                      │
│               └─► kb.status.entries.large   (1000+)                        │
│                       │                                                     │
│                       ▼                                                     │
│   command.kb.status.completed                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ KB CRAWL                                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   command.kb.crawl.started                                                  │
│       │                                                                     │
│       ├─► kb.crawl.source.{huggingface|pypi|npm|all}                       │
│       │                                                                     │
│       ├─► kb.crawl.db_init.created (if auto-init needed)                   │
│       │                                                                     │
│       ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │ HUGGINGFACE CRAWLER (if source includes)                            │  │
│   ├─────────────────────────────────────────────────────────────────────┤  │
│   │   kb.crawl.crawler.huggingface                                      │  │
│   │       │                                                              │  │
│   │       ├─► kb.crawl.huggingface.result.success (items added)         │  │
│   │       └─► kb.crawl.huggingface.errors.yes (had errors)              │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│       │                                                                     │
│       ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │ PYPI CRAWLER (if source includes)                                   │  │
│   ├─────────────────────────────────────────────────────────────────────┤  │
│   │   kb.crawl.crawler.pypi                                             │  │
│   │       │                                                              │  │
│   │       ├─► kb.crawl.pypi.result.success                              │  │
│   │       └─► kb.crawl.pypi.errors.yes                                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│       │                                                                     │
│       ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │ NPM CRAWLER (if source includes)                                    │  │
│   ├─────────────────────────────────────────────────────────────────────┤  │
│   │   kb.crawl.crawler.npm                                              │  │
│   │       │                                                              │  │
│   │       ├─► kb.crawl.npm.result.success                               │  │
│   │       └─► kb.crawl.npm.errors.yes                                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│       │                                                                     │
│       ▼                                                                     │
│   Overall Result:                                                           │
│   ├─► kb.crawl.result.success (items added)                                │
│   ├─► kb.crawl.result.empty (nothing added)                                │
│   └─► kb.crawl.had_errors.yes (errors occurred)                            │
│       │                                                                     │
│       ▼                                                                     │
│   command.kb.crawl.completed                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ KB LOOKUP                                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   command.kb.lookup.started                                                 │
│       │                                                                     │
│       ├─► kb.lookup.format.{json|text}                                     │
│       │                                                                     │
│       ▼                                                                     │
│   [Search KB]                                                               │
│       │                                                                     │
│       ├─► kb.lookup.result.found                                           │
│       │       ├─► kb.lookup.found_type.sdk                                 │
│       │       ├─► kb.lookup.found_type.model                               │
│       │       └─► kb.lookup.found_type.package                             │
│       │                                                                     │
│       └─► kb.lookup.result.not_found ──► EXIT: Not in KB (exit 1)         │
│               │                                                             │
│               ▼                                                             │
│   command.kb.lookup.completed                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Error Paths

All possible error scenarios across the application.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             ERROR PATHS                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ FILE SYSTEM ERRORS                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   error.{cmd}.file_not_found      Path doesn't exist                       │
│   error.{cmd}.permission_denied   No read/write access                     │
│   error.{cmd}.is_directory        Expected file, got directory             │
│   error.{cmd}.not_a_directory     Expected directory, got file             │
│   error.{cmd}.disk_full           Out of disk space                        │
│   error.{cmd}.symlink_loop        Circular symlink                         │
│                                                                             │
│   Recovery: Check path, permissions, disk space                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ MEMORY ERRORS                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   error.{cmd}.out_of_memory       System ran out of RAM                    │
│                                                                             │
│   Recovery: Scan smaller directory, increase memory                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ NETWORK ERRORS (enrichment)                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   enrichment.live_fetch_failed                                             │
│       ├─► network_error           Connection failed                        │
│       ├─► timeout                 Request timed out                        │
│       ├─► ssl_error               TLS/SSL issue                            │
│       ├─► rate_limited            429 - too many requests                  │
│       ├─► auth_error              401/403 - need token                     │
│       └─► server_error            5xx - API down                           │
│                                                                             │
│   Recovery: Check network, retry later, use --no-enrich                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ PARSE ERRORS                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   error.{cmd}.parse_error         Failed to parse file                     │
│   error.{cmd}.encoding_error      Character encoding issue                 │
│                                                                             │
│   Recovery: Check file format, report if valid file                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ DATABASE ERRORS                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   error.{cmd}.database_error      SQLite error                             │
│                                                                             │
│   Recovery: Re-init KB, check disk space                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Funnel Definitions

Pre-built funnels for analytics.

### Primary SBOM Generation Funnel

```
cli.started
    ↓
command.scan.started
    ↓
scan.format.cyclonedx  OR  scan.format.spdx
    ↓
scan.findings.{few|many}
    ↓
scan.enrich.enabled
    ↓
enrichment.kb_hit  OR  enrichment.live_fetch
    ↓
command.scan.completed (success=true)
```

**Drop-off points to monitor:**
- `scan.findings.none` → No AI found (wrong directory?)
- `enrichment.live_fetch_failed` → Network issues
- `error.scan.*` → Crashes

### Model Identification Funnel

```
cli.started
    ↓
command.identify.started
    ↓
identify.recognized.yes
    ↓
identify.kb_match.found
    ↓
command.identify.completed (success=true)
```

**Drop-off points:**
- `identify.recognized.no` → Unknown format
- `identify.kb_match.not_found` → Model not in KB

### KB Adoption Funnel

```
command.kb.init.started
    ↓
command.kb.init.completed
    ↓
kb.crawl.source.{huggingface|all}
    ↓
kb.crawl.result.success
    ↓
scan.kb_source.local
    ↓
enrichment.kb_hit
```

**Drop-off points:**
- `kb.crawl.result.empty` → Crawl failed
- `kb.crawl.*.errors.yes` → Partial failure

### Error Recovery Funnel

```
error.{cmd}.{category}
    ↓
cli.started (same session? retry)
    ↓
command.{cmd}.completed (success=true)
```

---

## 6. Key Metrics

| Metric | Calculation | Target |
|--------|-------------|--------|
| **SBOM Success Rate** | `scan.completed(success) / scan.started` | >95% |
| **Enrichment Hit Rate** | `enrichment.kb_hit / (kb_hit + live_fetch + not_found)` | >70% |
| **Model Recognition Rate** | `identify.recognized.yes / identify.started` | >80% |
| **KB Adoption** | `scan.kb_source.local / scan.enrich.enabled` | >50% |
| **Error Rate by Type** | `error.*.{category}` counts | <5% each |
| **Network Failure Rate** | `enrichment.live_fetch_failed / live_fetch` | <10% |

---

## 7. User Segments

| Segment | Identifying Events | Behavior |
|---------|-------------------|----------|
| **Compliance User** | `scan.format.cyclonedx` OR `scan.format.spdx` | Generates SBOMs |
| **Developer** | `scan.format.text` + `identify.*` | Exploring codebase |
| **CI/CD Pipeline** | `--no-enrich` flag, quiet mode | Automated scanning |
| **Power User** | `kb.crawl.*` + `scan.kb_source.local` | Local KB setup |
| **New User** | `cli.started` without `kb.init` | First-time use |
