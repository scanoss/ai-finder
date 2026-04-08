# SCANOSS AI Roadmap

## v0.1.x - MVP (COMPLETE)

**Goal:** Basic AI artifact scanning with SBOM generation.

**Features:**
- SDK detection (12 languages) via KB-driven patterns with fallback
- Model file parsing (12 formats: GGUF, SafeTensors, ONNX, PyTorch, TensorFlow, TFLite, CoreML, Keras, JAX, MXNet, Paddle, Pickle)
- Manifest dependency scanning (11 formats)
- License detection (osslili integration)
- Output formats: JSON, CycloneDX, SPDX
- CLI with scan, identify, kb commands
- Knowledge Base with 134 seeded SDK patterns

**Architecture:**
- KB-driven patterns with hardcoded fallback
- Extensible via KB updates (seed.db)

**Test Coverage:** 93% (296 tests)

---

## v0.2.x - Fingerprinting & Relationships (In Progress)

**Goal:** Component relationship analysis for comprehensive SBOM.

**Completed:**
- Tree-sitter integration for Python AST parsing
- PythonAnalyzer: detects AI SDK instantiations and method calls
- Function call graph extraction
- Component usage context tracking

**Pending:**
- Tree-sitter analyzers for other languages (JS, Go, Rust, etc.)
- Data flow tracking
- Component relationship graph builder
- Enhanced SBOM with `dependsOn`, `contains` relationships
- Model provenance detection (fine-tuned, merged, derived)

**Architecture:**
- Tree-sitter parsers per language
- In-memory graph for relationships
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
