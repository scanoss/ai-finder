# AI Finder - Executive Pitch

## The Problem

Organizations deploying AI face a critical blind spot: **they don't know what AI components are in their software**. With the EU AI Act requiring AI system documentation by August 2025, and supply chain attacks targeting AI dependencies (OWASP LLM Top 10 #3), this visibility gap is now a compliance and security risk.

## The Solution

**AI Finder** is an open-source AI artifact scanner that automatically discovers and documents AI components in your codebase—generating standards-compliant AI Bills of Materials (AIBOMs) for compliance and security.

## What We Detect

| Category | Coverage |
|----------|----------|
| **AI SDKs** | OpenAI, Anthropic, LangChain, HuggingFace, + 100 more across 12 languages |
| **Model Files** | GGUF, SafeTensors, ONNX, PyTorch, TensorFlow, + 6 more formats |
| **Dependencies** | AI packages in 11 package managers (PyPI, npm, Cargo, Maven, etc.) |
| **MCP Servers** | Model Context Protocol integrations and agent tools |

## Why AI Finder?

### vs. Snyk, Mend.io, Cycode, Cranium

| Differentiator | AI Finder | Competitors |
|----------------|------------|-------------|
| **Open Source** | MIT | Closed SaaS |
| **Language Coverage** | 12 languages | Python-focused |
| **Model Parsing** | 12 formats | Limited/None |
| **Dual SBOM Output** | CycloneDX + SPDX | Single format |
| **Offline Capable** | Embedded KB | Cloud required |
| **Pricing** | Free | $30-50+/user/month |

### Key Advantages

1. **Broadest Detection** - More languages and model formats than any competitor
2. **Standards First** - Both CycloneDX 1.5 and SPDX 2.3 for audit flexibility  
3. **Zero Lock-in** - Open source, self-hosted, works air-gapped
4. **Enterprise Ready** - Standalone binaries, no Python required at runtime
5. **EU AI Act Ready** - Built for compliance documentation requirements

## Technical Highlights

**Output includes:**
- Component PURLs (Package URLs)
- License detection (Apache, MIT, GPL, etc.)
- Download locations for provenance
- Dependency relationships
- Model metadata (architecture, parameters, quantization)

## Roadmap

**Now (v0.2.x)**
- Full SDK/model/manifest detection
- CycloneDX + SPDX output
- Standalone binaries

**Next (v1.x)**
- Dataset detection
- KB cloud sync

**Future (v2.x)**
- EU AI Act reporting
- Model provenance
- Risk scoring?
