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

**Test Coverage:** 91% (320 tests)

---

## v0.2.x - Component Relationships (COMPLETE)

**Goal:** Component relationship analysis for comprehensive SBOM.

**Features:**
- Tree-sitter integration for Python AST parsing
- PythonAnalyzer: detects AI SDK instantiations and method calls
- JavaScriptAnalyzer: JS/TS/JSX/TSX SDK detection
- GoAnalyzer: package.Function() and method call detection
- RustAnalyzer: scoped calls and method detection
- Function call graph extraction
- Component usage context tracking
- ComponentGraph with nodes (sdk/function/file) and edges (dependsOn/contains)
- RelationshipAnalyzer orchestrating all language analyzers
- CycloneDX dependencies array from graph
- SPDX DEPENDS_ON/CONTAINS relationships
- DataFlowGraph for tracking AI component output propagation
- Taint tracking (variables holding AI SDK outputs)

**Test Coverage:** 91% (325 tests)

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
- Training data inference
- Risk scoring
- Vulnerability correlation

---

## v2.0.x - Fingerprinting (Future)

**Goal:** Model fingerprinting and provenance detection.

**Features:**
- Model similarity detection (TLSH)
- Model provenance detection (fine-tuned, merged, derived)
- Model fingerprint database
- Known model identification
