#!/usr/bin/env python3
"""Create seed database with essential AI SDK patterns."""

import json
import sys
from pathlib import Path

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/ai-finder-kb/src"))

from ai_finder_kb.database import Database

SEED_DB_PATH = (
    Path(__file__).parent.parent / "packages/ai-finder-kb/src/ai_finder_kb/data/seed.db"
)

# SDK patterns by language/ecosystem
SDKS = [
    # Python SDKs
    {
        "id": "openai-python",
        "purl": "pkg:pypi/openai",
        "patterns": ["openai", "from openai", "import openai"],
        "category": "llm-client",
        "license": "Apache-2.0",
    },
    {
        "id": "anthropic-python",
        "purl": "pkg:pypi/anthropic",
        "patterns": ["anthropic", "from anthropic", "import anthropic"],
        "category": "llm-client",
        "license": "MIT",
    },
    {
        "id": "google-genai-python",
        "purl": "pkg:pypi/google-generativeai",
        "patterns": ["google.generativeai", "import google.generativeai"],
        "category": "llm-client",
        "license": "Apache-2.0",
    },
    {
        "id": "langchain-python",
        "purl": "pkg:pypi/langchain",
        "patterns": ["langchain", "from langchain", "import langchain"],
        "category": "framework",
        "license": "MIT",
    },
    {
        "id": "llama-index-python",
        "purl": "pkg:pypi/llama-index",
        "patterns": ["llama_index", "from llama_index", "import llama_index"],
        "category": "framework",
        "license": "MIT",
    },
    {
        "id": "transformers-python",
        "purl": "pkg:pypi/transformers",
        "patterns": ["transformers", "from transformers", "import transformers"],
        "category": "ml-framework",
        "license": "Apache-2.0",
    },
    {
        "id": "huggingface-hub-python",
        "purl": "pkg:pypi/huggingface-hub",
        "patterns": ["huggingface_hub", "from huggingface_hub"],
        "category": "ml-framework",
        "license": "Apache-2.0",
    },
    {
        "id": "torch-python",
        "purl": "pkg:pypi/torch",
        "patterns": ["torch", "import torch", "from torch"],
        "category": "ml-framework",
        "license": "BSD-3-Clause",
    },
    {
        "id": "tensorflow-python",
        "purl": "pkg:pypi/tensorflow",
        "patterns": ["tensorflow", "import tensorflow", "from tensorflow"],
        "category": "ml-framework",
        "license": "Apache-2.0",
    },
    {
        "id": "keras-python",
        "purl": "pkg:pypi/keras",
        "patterns": ["keras", "import keras", "from keras"],
        "category": "ml-framework",
        "license": "Apache-2.0",
    },
    # JavaScript/TypeScript SDKs
    {
        "id": "openai-js",
        "purl": "pkg:npm/openai",
        "patterns": ["from 'openai'", 'from "openai"', "require('openai')"],
        "category": "llm-client",
        "license": "Apache-2.0",
    },
    {
        "id": "anthropic-js",
        "purl": "pkg:npm/@anthropic-ai/sdk",
        "patterns": ["@anthropic-ai/sdk", "from '@anthropic-ai/sdk'"],
        "category": "llm-client",
        "license": "MIT",
    },
    {
        "id": "langchain-js",
        "purl": "pkg:npm/langchain",
        "patterns": ["from 'langchain'", 'from "langchain"', "require('langchain')"],
        "category": "framework",
        "license": "MIT",
    },
    {
        "id": "vercel-ai-js",
        "purl": "pkg:npm/ai",
        "patterns": ["from 'ai'", 'from "ai"', "@vercel/ai"],
        "category": "framework",
        "license": "Apache-2.0",
    },
    # Go SDKs
    {
        "id": "openai-go",
        "purl": "pkg:golang/github.com/sashabaranov/go-openai",
        "patterns": ["github.com/sashabaranov/go-openai", "go-openai"],
        "category": "llm-client",
        "license": "Apache-2.0",
    },
    {
        "id": "anthropic-go",
        "purl": "pkg:golang/github.com/anthropics/anthropic-sdk-go",
        "patterns": ["anthropic-sdk-go", "anthropics/anthropic-sdk-go"],
        "category": "llm-client",
        "license": "MIT",
    },
    # Rust SDKs
    {
        "id": "async-openai-rust",
        "purl": "pkg:cargo/async-openai",
        "patterns": ["async_openai", "async-openai"],
        "category": "llm-client",
        "license": "MIT",
    },
    # Java SDKs
    {
        "id": "openai-java",
        "purl": "pkg:maven/com.theokanning.openai-gpt3-java/api",
        "patterns": ["com.theokanning.openai", "openai-gpt3-java"],
        "category": "llm-client",
        "license": "MIT",
    },
    {
        "id": "langchain4j",
        "purl": "pkg:maven/dev.langchain4j/langchain4j",
        "patterns": ["dev.langchain4j", "langchain4j"],
        "category": "framework",
        "license": "Apache-2.0",
    },
    # Ruby SDKs
    {
        "id": "ruby-openai",
        "purl": "pkg:gem/ruby-openai",
        "patterns": ["ruby-openai", "OpenAI::Client"],
        "category": "llm-client",
        "license": "MIT",
    },
    # PHP SDKs
    {
        "id": "openai-php",
        "purl": "pkg:composer/openai-php/client",
        "patterns": ["openai-php/client", "OpenAI\\Client"],
        "category": "llm-client",
        "license": "MIT",
    },
]

# MCP servers
MCP_SERVERS = [
    {
        "id": "mcp-filesystem",
        "purl": "pkg:npm/@modelcontextprotocol/server-filesystem",
        "patterns": ["@modelcontextprotocol/server-filesystem"],
        "description": "MCP server for filesystem access",
    },
    {
        "id": "mcp-github",
        "purl": "pkg:npm/@modelcontextprotocol/server-github",
        "patterns": ["@modelcontextprotocol/server-github"],
        "description": "MCP server for GitHub integration",
    },
    {
        "id": "mcp-postgres",
        "purl": "pkg:npm/@modelcontextprotocol/server-postgres",
        "patterns": ["@modelcontextprotocol/server-postgres"],
        "description": "MCP server for PostgreSQL database access",
    },
    {
        "id": "mcp-sqlite",
        "purl": "pkg:npm/@modelcontextprotocol/server-sqlite",
        "patterns": ["@modelcontextprotocol/server-sqlite"],
        "description": "MCP server for SQLite database access",
    },
    {
        "id": "mcp-slack",
        "purl": "pkg:npm/@modelcontextprotocol/server-slack",
        "patterns": ["@modelcontextprotocol/server-slack"],
        "description": "MCP server for Slack integration",
    },
]

# Sample models
MODELS = [
    {
        "purl": "pkg:huggingface/TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        "name": "TinyLlama-1.1B-Chat-v1.0",
        "organization": "TinyLlama",
        "architecture": "llama",
        "parameter_count": 1100000000,
        "license": "Apache-2.0",
    },
    {
        "purl": "pkg:huggingface/meta-llama/Llama-2-7b",
        "name": "Llama-2-7b",
        "organization": "meta-llama",
        "architecture": "llama",
        "parameter_count": 7000000000,
        "license": "LLAMA 2 COMMUNITY LICENSE",
    },
    {
        "purl": "pkg:huggingface/mistralai/Mistral-7B-v0.1",
        "name": "Mistral-7B-v0.1",
        "organization": "mistralai",
        "architecture": "mistral",
        "parameter_count": 7000000000,
        "license": "Apache-2.0",
    },
    {
        "purl": "pkg:huggingface/microsoft/phi-2",
        "name": "phi-2",
        "organization": "microsoft",
        "architecture": "phi",
        "parameter_count": 2700000000,
        "license": "MIT",
    },
    {
        "purl": "pkg:huggingface/google/gemma-2b",
        "name": "gemma-2b",
        "organization": "google",
        "architecture": "gemma",
        "parameter_count": 2000000000,
        "license": "gemma",
    },
]


def main() -> None:
    """Create seed database."""
    print(f"Creating seed database at {SEED_DB_PATH}")

    # Remove existing seed.db if it exists
    if SEED_DB_PATH.exists():
        SEED_DB_PATH.unlink()

    with Database(SEED_DB_PATH) as db:
        db.initialize()

        # Insert SDKs
        for sdk in SDKS:
            db.execute(
                "INSERT INTO sdks (id, purl, patterns, category, license) VALUES (?, ?, ?, ?, ?)",
                (
                    sdk["id"],
                    sdk["purl"],
                    json.dumps(sdk["patterns"]),
                    sdk["category"],
                    sdk["license"],
                ),
            )
        print(f"Inserted {len(SDKS)} SDKs")

        # Insert MCP servers
        for mcp in MCP_SERVERS:
            db.execute(
                "INSERT INTO mcp_servers (id, purl, patterns, description) VALUES (?, ?, ?, ?)",
                (
                    mcp["id"],
                    mcp["purl"],
                    json.dumps(mcp["patterns"]),
                    mcp["description"],
                ),
            )
        print(f"Inserted {len(MCP_SERVERS)} MCP servers")

        # Insert models
        for model in MODELS:
            db.execute(
                "INSERT INTO models "
                "(purl, name, organization, architecture, parameter_count, license) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    model["purl"],
                    model["name"],
                    model["organization"],
                    model["architecture"],
                    model["parameter_count"],
                    model["license"],
                ),
            )
        print(f"Inserted {len(MODELS)} models")

        db.commit()

    print("Seed database created successfully!")


if __name__ == "__main__":
    main()
