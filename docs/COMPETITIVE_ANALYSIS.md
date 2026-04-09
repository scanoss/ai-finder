# SCANOSS AI - Competitive Analysis & Product Overview

## Executive Summary

**SCANOSS AI** is an open-source AI artifact scanner for software supply chain security and EU AI Act compliance. It detects AI/ML components in codebases—SDKs, models, agents, and MCP servers—and generates standards-compliant SBOMs (CycloneDX, SPDX).

### Key Differentiators

| Advantage | SCANOSS AI | Most Competitors |
|-----------|------------|------------------|
| **Open Source** | Apache 2.0 licensed, CLI + library | SaaS-only, closed source |
| **Language Coverage** | 12 languages | Python-focused (most) |
| **Model Formats** | 12 formats (GGUF, SafeTensors, ONNX, etc.) | Limited or none |
| **Dual SBOM Output** | CycloneDX 1.5 + SPDX 2.3 | Usually single format |
| **Offline Capable** | Embedded KB, works air-gapped | Requires cloud connectivity |
| **Relationship Analysis** | Tree-sitter based dependency graphs | Limited or none |
| **Pricing** | Free / Open Source | $30-50+/user/month |

---

## Why SCANOSS AI?

1. **Open Source First** - No vendor lock-in, audit the code yourself
2. **Broadest Coverage** - 12 languages, 12 model formats, 11 package managers
3. **Standards Compliant** - Both CycloneDX and SPDX output
4. **Works Anywhere** - Offline capable with embedded KB
5. **Enterprise Ready** - Standalone binaries, no runtime dependencies
6. **EU AI Act Ready** - Built for compliance documentation

---

## What SCANOSS AI Detects

### 1. SDK/Library Detection (12 Languages)

| Language | AI SDKs Detected |
|----------|-----------------|
| Python | OpenAI, Anthropic, Cohere, LangChain, LlamaIndex, HuggingFace, CrewAI, Strands Agents |
| JavaScript/TypeScript | OpenAI, Anthropic, LangChain.js, Vercel AI SDK |
| Go | OpenAI-go, Anthropic-go |
| Rust | async-openai, anthropic-rs |
| Java | OpenAI Java, LangChain4j |
| Kotlin | OpenAI Kotlin |
| Ruby | ruby-openai |
| PHP | openai-php |
| C# | OpenAI .NET, Semantic Kernel |
| Swift | OpenAI Swift |
| Scala | OpenAI Scala |
| C++ | OpenAI C++ |

### 2. Model File Parsing (12 Formats)

| Format | Extensions | Metadata Extracted |
|--------|-----------|-------------------|
| GGUF | .gguf | Architecture, quantization, parameters |
| SafeTensors | .safetensors | Tensor info, model architecture |
| ONNX | .onnx | Graph structure, operators |
| PyTorch | .pt, .pth, .bin | State dict, model structure |
| TensorFlow | .pb, SavedModel | Graph def, signatures |
| TFLite | .tflite | Operators, tensors |
| Keras | .h5, .keras | Layer config, weights |
| CoreML | .mlmodel, .mlpackage | Model type, features |
| JAX | .orbax | Checkpoints |
| MXNet | .params | Parameters |
| PaddlePaddle | .pdparams | Parameters |
| Pickle | .pkl | Serialized objects |

### 3. Manifest Parsing (11 Package Managers)

| Ecosystem | Files Parsed |
|-----------|-------------|
| Python | requirements.txt, pyproject.toml, setup.py, Pipfile |
| npm | package.json, package-lock.json, yarn.lock |
| Go | go.mod, go.sum |
| Rust | Cargo.toml, Cargo.lock |
| Maven | pom.xml |
| Gradle | build.gradle, build.gradle.kts |
| Ruby | Gemfile, Gemfile.lock |
| PHP | composer.json, composer.lock |
| Swift | Package.swift |
| CocoaPods | Podfile |
| NuGet | *.csproj, packages.config |

### 4. MCP Server Detection

- Detects MCP (Model Context Protocol) server configurations
- Identifies AI tool integrations
- Maps agent-to-tool relationships

---

## Output Formats

| Format | Version | Features |
|--------|---------|----------|
| **CycloneDX** | 1.5 | Full component metadata, licenses, PURLs, relationships |
| **SPDX** | 2.3 | Package info, licenses, external refs, download locations |
| **JSON** | Custom | Raw scan results with all metadata |
| **Text** | Human-readable | Summary output for quick review |

---

## Enrichment & Intelligence

### Knowledge Base (Embedded)
- 134+ AI SDKs catalogued
- 5+ AI models with metadata
- MCP server registry
- Auto-initialization from seed database

### Live API Fallback
- PyPI package metadata
- npm package metadata
- HuggingFace model info
- License detection via osslili

### Relationship Analysis (Tree-sitter)
- Component dependency graphs
- SDK usage tracking across files
- Caller/callee relationships
- Data flow analysis

---

## Competitive Comparison

| Capability | SCANOSS AI | Snyk | Mend.io | Cycode | Cranium | Cisco |
|------------|------------|------|---------|--------|---------|-------|
| **Open Source** | Yes | No | No | No | No | No |
| **Languages** | 12 | Python* | Multi | Multi | Multi | Python* |
| **Model Parsing** | 12 formats | Limited | No | No | Yes | No |
| **CycloneDX** | Yes | Yes | Yes | Yes | Yes | Yes |
| **SPDX** | Yes | No | Yes | No | No | No |
| **MCP Detection** | Yes | Yes | Yes | Yes | No | Yes |
| **Offline Mode** | Yes | No | No | No | No | No |
| **Relationship Graphs** | Yes | Yes | No | No | No | No |
| **EU AI Act Ready** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Pricing** | Free | $$$  | $$$ | $$$ | $$$ | $$$ |

*Python-focused for source analysis

### Competitor Deep Dive

**Snyk AI-BOM**
- Strong Python deep code analysis
- CycloneDX output
- Finds AI usage without manifest references
- Limited to Python ecosystem publicly

**Mend.io**
- Focus on AI-generated code detection
- Agent config scanning (prompt injection)
- Risk quantification over inventory
- 2026 EU compliance workflows

**Cycode**
- Broader AppSec platform (Gartner #1 Software Supply Chain)
- AI/ML Inventory in early access
- Traces AI assets to source repos
- Shadow AI discovery

**Cranium AI**
- Strong GRC integration (Archer)
- Compliance scoring (EU AI Act, NIST AI RMF)
- AgentSensor for agentic AI (2025)
- 11 Gartner Hype Cycle mentions

**Manifest Cyber**
- First dedicated AI transparency platform
- Model provenance and training data
- FedRAMP High authorized
- Fortune 500/government focus

**Cisco AI Defense**
- Enterprise network integration
- DefenseClaw framework (2026)
- MCP Catalog
- Agentic workflow guardrails

---

## Roadmap

### Current (v0.2.x)
- [x] 12-language SDK detection
- [x] 12 model format parsing
- [x] CycloneDX 1.5 + SPDX 2.3 output
- [x] Embedded knowledge base
- [x] MCP server detection
- [x] Tree-sitter relationship analysis
- [x] PyPI/npm live enrichment
- [x] Standalone binaries (macOS, Linux, Windows)

### Planned (v1.x)
- [ ] Dataset detection (training data transparency)
- [ ] Model card generation (CycloneDX ML-BOM)
- [ ] HuggingFace model fingerprinting
- [ ] KB sync from SCANOSS cloud
- [ ] VS Code extension

### Future (v2.x)
- [ ] EU AI Act compliance reporting
- [ ] Model provenance tracking
- [ ] Supply chain risk scoring
- [ ] Agent behavior analysis
- [ ] Prompt injection detection

---

## EU AI Act Compliance

SCANOSS AI supports EU AI Act compliance through:

| Requirement | SCANOSS AI Capability |
|-------------|----------------------|
| AI System Inventory | SDK, model, and agent detection |
| Component Transparency | SBOM generation (CycloneDX/SPDX) |
| License Compliance | Automated license detection |
| Supply Chain Documentation | Dependency and relationship mapping |
| Technical Documentation | Model metadata extraction |

---

*Last updated: April 2026*
