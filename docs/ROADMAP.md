# SCANOSS AI Roadmap

## v0.1.x - MVP (Current)

**Goal:** Basic AI artifact scanning with SBOM generation.

**Features:**
- SDK detection (11 languages) via KB-driven patterns
- Model file parsing (GGUF, SafeTensors, ONNX, PyTorch)
- Manifest dependency scanning (8 formats)
- License detection (osslili integration)
- Output formats: JSON, CycloneDX, SPDX
- CLI and standalone binaries

**Architecture:**
- Patterns stored in KB (seed.db), not hardcoded
- Extensible via KB updates (future API sync)

---

## v0.2.x - Fingerprinting & Relationships (Planned)

**Goal:** Component relationship analysis for comprehensive SBOM.

**Features:**
- Tree-sitter integration for AST parsing
- Call graph analysis (who calls what)
- Data flow tracking
- Component relationship graph
- Enhanced SBOM with dependency relationships
- Model provenance detection (fine-tuned, merged, derived)

**Architecture:**
- Tree-sitter parsers per language
- Graph database or in-memory graph for relationships
- SBOM includes `dependsOn`, `contains` relationships

---

## v1.0.x - Enterprise (Future)

**Goal:** Production-ready for enterprise deployment.

**Features:**
- KB sync API (automatic pattern updates)
- Apple code signing for binaries
- Policy engine (compliance rules)
- CI/CD integrations (GitHub Action, GitLab CI)
- Detailed reporting and dashboards

---

## v1.1.x - Advanced Analysis (Future)

**Goal:** Deep analysis capabilities.

**Features:**
- Model similarity detection (TLSH)
- Training data inference
- Risk scoring
- Vulnerability correlation
