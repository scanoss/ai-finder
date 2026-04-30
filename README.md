# ai-finder

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

> AI artifact scanner for supply chain security and compliance

## About

**ai-finder** detects AI/ML artifacts in codebases for:

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
| Java/Kotlin | openai-java, LangChain4j, Spring AI |
| And more... | Ruby, PHP, C#, C++, Swift, Scala, Kotlin |

### AI Package Detection (134+ packages)

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
- **CycloneDX 1.6** - OWASP SBOM format with ML-BOM support
- **SPDX 2.3** - Linux Foundation SBOM format
- **SPDX 3.0** - Latest SPDX specification with JSON-LD

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

```bash
pip install ai-finder
```

Requires Python 3.9 or later.

## Usage

```bash
# Scan a directory
ai-finder scan /path/to/project

# Generate SBOM (CycloneDX)
ai-finder scan /path/to/project -f cyclonedx -o sbom.json

# Generate SBOM (SPDX)
ai-finder scan /path/to/project -f spdx -o sbom.spdx.json

# Identify a model file
ai-finder identify model.gguf

# Initialize local KB
ai-finder kb init

# Lookup model by PURL
ai-finder kb lookup pkg:huggingface/TinyLlama/TinyLlama-1.1B-Chat-v1.0
```

## Telemetry

This tool collects anonymous usage telemetry to help improve the product. No file paths, code content, or scan targets are collected.

**Disable telemetry:**
```bash
# Per-session
ai-finder --no-telemetry scan .

# Environment variable
export AI_FINDER_TELEMETRY=0

# Or use the standard
export DO_NOT_TRACK=1
```

See [docs/TELEMETRY.md](docs/TELEMETRY.md) for full details on what is collected.

## Development

```bash
# Clone repository
git clone https://github.com/scanoss/ai-finder.git
cd ai-finder

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

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

Copyright (c) 2026 SCANOSS.
