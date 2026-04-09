# scanoss-ai

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

> AI artifact scanner for supply chain security and compliance

## About

**scanoss-ai** detects AI/ML artifacts in codebases for:

- **Supply Chain Security** - Identify AI models, SDKs, and dependencies
- **EU AI Act Compliance** - Generate SBOM reports for regulatory requirements
- **Risk Assessment** - Detect API keys, model provenance, and usage patterns

## Features

### SDK Detection (12 languages)

| Language | SDKs Detected |
|----------|---------------|
| Python | OpenAI, Anthropic, HuggingFace, LangChain, LlamaIndex, Strands, CrewAI, AutoGen |
| JavaScript/TypeScript | OpenAI, Anthropic, LangChain, Vercel AI SDK |
| Go | go-openai, go-anthropic |
| Rust | async-openai, anthropic-rs |
| Java | openai-java, LangChain4j, Spring AI |
| And more... | Ruby, PHP, C#, C++, Swift, Scala |

### AI Package Detection (116+ packages)

Comprehensive detection across categories:

| Category | Packages |
|----------|----------|
| **LLM Clients** | OpenAI, Anthropic, Cohere, Groq, Mistral, Ollama, Google GenAI, Azure OpenAI |
| **Agent Frameworks** | LangChain, LlamaIndex, Strands Agents, CrewAI, AutoGen, Semantic Kernel |
| **ML Frameworks** | PyTorch, TensorFlow, Keras, JAX, Transformers, scikit-learn, XGBoost |
| **Vector Databases** | ChromaDB, Pinecone, Weaviate, Qdrant, Milvus, FAISS, LanceDB |
| **Speech/Audio AI** | OpenAI Whisper, Faster Whisper, ElevenLabs, Bark |
| **AI Safety** | AIProxyGuard, Guardrails AI, NeMo Guardrails, LLM Guard |
| **Tools & Utilities** | Tavily, LangSmith, W&B, MLflow, Accelerate, Datasets |
| **MCP/Tool Use** | MCP, Anthropic Tools |

### Model File Detection (12 formats)

GGUF, SafeTensors, ONNX, PyTorch, TensorFlow, TFLite, CoreML, JAX, Keras, MXNet, PaddlePaddle

### Manifest Parsing (11 formats)

requirements.txt, pyproject.toml, package.json, go.mod, Cargo.toml, pom.xml, build.gradle, Gemfile, composer.json, *.csproj, Package.swift

### Output Formats

- **JSON** - Machine-readable findings
- **CycloneDX 1.5** - OWASP SBOM format with ML-BOM support
- **SPDX 2.3** - Linux Foundation SBOM format

## SBOM Compliance

Generated SBOMs are compliant with major standards:

| Standard | Status | Notes |
|----------|--------|-------|
| **CISA Minimum SBOM Elements** | Compliant | Supplier, name, version, PURL, timestamp, author |
| **OpenChain ISO/IEC 5230** | Compliant | Document namespace, SPDX-License-Identifier, creator info |
| **EU AI Act** | Ready | License info, descriptions, external references for AI components |
| **CycloneDX ML-BOM** | Supported | modelCard, modelParameters, architecture metadata |

### License Handling

- Licenses are automatically enriched from PyPI, npm, and HuggingFace
- Unknown licenses are marked as `NOASSERTION` per SPDX specification
- Supports SPDX license expressions

## Installation

### Standalone Binary (Recommended)

Download the pre-built binary for your platform from [GitHub Releases](https://github.com/scanoss/scanoss-ai/releases):

| Platform | Binary |
|----------|--------|
| macOS (Apple Silicon) | `scanoss-ai-macos-arm64` |
| macOS (Intel) | `scanoss-ai-macos-x64` |
| Linux (x86_64) | `scanoss-ai-linux-x64` |
| Windows | `scanoss-ai-windows-x64.exe` |

```bash
# macOS - remove quarantine attribute first
xattr -d com.apple.quarantine scanoss-ai-macos-arm64
chmod +x scanoss-ai-macos-arm64
./scanoss-ai-macos-arm64 --version

# Linux
chmod +x scanoss-ai-linux-x64
./scanoss-ai-linux-x64 --version

# Windows
scanoss-ai-windows-x64.exe --version
```

> **Note (macOS):** The binary is not yet Apple-signed. macOS Gatekeeper will show a warning on first run. Use the `xattr` command above to remove the quarantine flag, or right-click the file and select "Open" to bypass.

No Python installation required - all dependencies are bundled.

### From PyPI

```bash
pip install scanoss-ai
```

## Usage

```bash
# Scan a directory
scanoss-ai scan /path/to/project

# Generate SBOM (CycloneDX)
scanoss-ai scan /path/to/project -f cyclonedx -o sbom.json

# Generate SBOM (SPDX)
scanoss-ai scan /path/to/project -f spdx -o sbom.spdx.json

# Identify a model file
scanoss-ai identify model.gguf

# Initialize local KB
scanoss-ai kb init

# Lookup model by PURL
scanoss-ai kb lookup pkg:huggingface/TinyLlama/TinyLlama-1.1B-Chat-v1.0
```

## Telemetry

This tool collects anonymous usage telemetry. See [docs/TELEMETRY.md](docs/TELEMETRY.md) for details and opt-out instructions.

## Development

```bash
# Clone repository
git clone https://github.com/scanoss/scanoss-ai.git
cd scanoss-ai

# Install with uv
uv sync --all-packages --all-extras

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

## Security

If you discover a security vulnerability, please follow our [Security Policy](SECURITY.md).

## License

This project is licensed under the Apache License 2.0 - see [LICENSE](LICENSE) for details.

Copyright (c) 2025-2026 SCANOSS. All Rights Reserved.
