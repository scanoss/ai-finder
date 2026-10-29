# AI-Finder: Supply Chain Security and Compliance Scanning for AI

[![PyPI](https://img.shields.io/pypi/v/ai-finder.svg)](https://pypi.org/project/ai-finder/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Secure your AI supply chain and automate compliance scanning for models and components with AI-Finder.**

AI-Finder is an open-source scanner that finds the AI in a codebase (AI models, AI SDKs, agent frameworks and MCP servers) and writes it into an **AI bill of materials (AI-BOM)** in CycloneDX or SPDX. Every finding records which package it is, its version and licence, and the file and line where it is used, so security, legal and compliance teams can see exactly which AI components ship in a product.

```bash
pip install ai-finder
ai-finder scan . -f cyclonedx -o aibom.json
```

## Why AI-Finder

- **Know what AI you ship.** It finds models, SDKs, MCP servers, agents and tools across 12 programming languages, in source code, dependency manifests and MCP client configs.
- **Prove where each component came from.** Every component carries a package URL (purl), version, licence and supplier where known, plus evidence of each place it was found.
- **Plug into the tools you already use.** Output is a standard SBOM in CycloneDX 1.6 (including ML-BOM model cards), SPDX 2.3 or SPDX 3.0, so any SBOM or vulnerability tool can read it.
- **Run it anywhere.** It's a single command-line tool with no account and no server, and it runs on your machine or in CI.

## What it detects

- **AI SDKs and frameworks.** It reads imports in Python, JavaScript/TypeScript, Go, Rust, Java, Kotlin, Scala, Ruby, PHP, C#, C/C++ and Swift, and matches them against a knowledge base of 200+ SDKs: OpenAI, Anthropic, Google GenAI, LangChain, LlamaIndex, Strands Agents, CrewAI, AutoGen, PyTorch, Transformers, vector databases, guardrails and more. An import is resolved to the package that provides it, so `import strands` is reported as `strands-agents`.
- **MCP servers and clients.** It finds Model Context Protocol servers in three places:
  - MCP client configs: Claude Desktop, `.mcp.json`, VS Code, Cursor, Cline and Windsurf.
  - Servers built with the MCP SDKs.
  - Servers launched from code with `npx`, `uvx`, `pipx` or `docker`.

  Each one is identified against 2,400+ known MCP servers from the official MCP Registry. A server that isn't on the list is still reported.
- **AI model files.** It reads 12 formats, including GGUF, SafeTensors, ONNX, PyTorch, TensorFlow, TFLite, Core ML and Keras. Model files are identified by content hash against 26,000+ known models, so a generically named shard still resolves to the model it belongs to.
- **AI dependencies.** It finds AI packages declared in 11 manifest formats, including `requirements.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `pom.xml` and `build.gradle`.
- **Agents, tools, embeddings, vector stores and datasets** used in code.

## Usage

```bash
# Scan a project and print a summary
ai-finder scan /path/to/project

# AI-BOM as CycloneDX 1.6
ai-finder scan /path/to/project -f cyclonedx -o aibom.cdx.json

# AI-BOM as SPDX 3.0 (or --spdx-v2 for SPDX 2.3)
ai-finder scan /path/to/project -f spdx --spdx-v3 -o aibom.spdx.json

# Identify a single model file
ai-finder identify model.gguf

# Update the knowledge base of SDKs, MCP servers and models
ai-finder kb update
```

## What a finding looks like

An MCP server declared in a project's `.mcp.json`, as it appears in the CycloneDX output:

```json
{
  "type": "application",
  "name": "@modelcontextprotocol/server-github",
  "purl": "pkg:npm/modelcontextprotocol/server-github",
  "properties": [
    { "name": "ai-finder:mcp:role", "value": "server" },
    { "name": "ai-finder:mcp:source", "value": "config" },
    { "name": "ai-finder:mcp:transport", "value": "stdio" }
  ],
  "evidence": {
    "occurrences": [
      { "location": ".mcp.json", "line": 1,
        "additionalContext": "npx @modelcontextprotocol/server-github" }
    ]
  }
}
```

Secrets stay out of the AI-BOM. Environment variables, launch arguments and URL credentials from MCP configs are never copied into it.

## Compliance

AI-Finder produces the inventory that AI governance work starts from:

- **SBOM standards.** CycloneDX 1.6 with ML-BOM model cards, SPDX 2.3 and SPDX 3.0. Components carry supplier, name, version, purl and licence where they are known, and `NOASSERTION` where they are not, following the SPDX convention.
- **Licences.** Licences come from the package registries (PyPI, npm, Hugging Face) as SPDX expressions, which supports open-source licence compliance reviews.
- **AI regulation.** A complete list of the models and AI components in a product is the starting point for documentation under frameworks such as the EU AI Act.

## Knowledge base

Detection is driven by a local knowledge base of SDKs, MCP servers and models that ships with the package. `ai-finder kb update` downloads the latest version, which is refreshed from the package registries and the MCP Registry. It adds new entries and removes ones that no longer exist.

**Limitations.** AI-Finder identifies components and models by exact matching: package and import names for components, and file hashes and names for models. It cannot identify a component or model that has been modified, quantized, fine-tuned or retrained, because those change the very things it matches on. For those cases, [AI-Finder Pro from SCANOSS](https://scanoss.com) adds fingerprint matching for AI.

## Privacy

- **Your code never leaves your machine.** The scan runs locally.
- **Registry lookups.** With enrichment on (the default), package and model names are looked up on PyPI, npm and Hugging Face to fill in licence and supplier. Use `--no-enrich` to skip these lookups.
- **Telemetry.** Anonymous usage telemetry is collected, with no file paths, code or scan targets. Turn it off with `--no-telemetry`, `AI_FINDER_TELEMETRY=0` or `DO_NOT_TRACK=1`. See [docs/TELEMETRY.md](https://github.com/scanoss/ai-finder/blob/main/docs/TELEMETRY.md) for exactly what is sent.

## FAQ

**What is an AI-BOM?**
An AI bill of materials is an SBOM that covers AI components: the models, AI SDKs, agent frameworks and MCP servers a product depends on, with their versions, licences and origins.

**Does AI-Finder detect MCP servers?**
Yes. It finds them in MCP client configs, in code that builds servers or clients with the MCP SDKs, and in code that launches them. Each one is reported with its package, transport and the file and line it came from.

**Which SBOM formats are supported?**
CycloneDX 1.6, SPDX 2.3 and SPDX 3.0, plus plain JSON and a text summary.

**Which languages are supported?**
SDK imports are detected in Python, JavaScript/TypeScript, Go, Rust, Java, Kotlin, Scala, Ruby, PHP, C#, C/C++ and Swift. MCP servers and clients are detected in Python and JavaScript/TypeScript code, and in MCP client configs regardless of language.

**Can AI-Finder detect modified, retrained, fine-tuned or quantized models?**
No. Recognising a model after it has been changed needs fingerprint matching, which this version does not include. [Contact SCANOSS](https://scanoss.com) for AI-Finder Pro, which adds that layer.

## Contributing

Contributions are welcome. [CONTRIBUTING.md](https://github.com/scanoss/ai-finder/blob/main/CONTRIBUTING.md) covers the development setup, tests and pull request process.

## Security

To report a vulnerability, follow the [Security Policy](https://github.com/scanoss/ai-finder/blob/main/SECURITY.md).

## License

MIT. See [LICENSE](https://github.com/scanoss/ai-finder/blob/main/LICENSE). Copyright (c) 2026 SCANOSS.
