"""Tests for SDK detectors."""

from __future__ import annotations

from pathlib import Path

import pytest
from scanoss_ai_scanner.detectors.go import GoDetector
from scanoss_ai_scanner.detectors.java import JavaDetector
from scanoss_ai_scanner.detectors.javascript import JavaScriptDetector
from scanoss_ai_scanner.detectors.python import PythonDetector
from scanoss_ai_scanner.detectors.ruby import RubyDetector
from scanoss_ai_scanner.detectors.rust import RustDetector
from scanoss_ai_scanner.models import FindingType


@pytest.fixture
def python_detector() -> PythonDetector:
    return PythonDetector()


class TestPythonDetector:
    def test_supported_extensions(self, python_detector: PythonDetector) -> None:
        assert ".py" in python_detector.extensions

    def test_detect_import_openai(self, python_detector: PythonDetector) -> None:
        code = "import openai"
        findings = list(python_detector.detect(code, Path("main.py")))

        assert len(findings) == 1
        assert findings[0].type == FindingType.SDK_USAGE
        assert findings[0].sdk_usage is not None
        assert findings[0].sdk_usage.sdk == "openai"
        assert findings[0].sdk_usage.import_statement == "import openai"

    def test_detect_from_import(self, python_detector: PythonDetector) -> None:
        code = "from anthropic import Anthropic"
        findings = list(python_detector.detect(code, Path("main.py")))

        assert len(findings) == 1
        assert findings[0].sdk_usage is not None
        assert findings[0].sdk_usage.sdk == "anthropic"

    def test_detect_multiple_imports(self, python_detector: PythonDetector) -> None:
        code = """import openai
from anthropic import Anthropic
from langchain import LLMChain
"""
        findings = list(python_detector.detect(code, Path("main.py")))

        sdks = {f.sdk_usage.sdk for f in findings if f.sdk_usage}
        assert "openai" in sdks
        assert "anthropic" in sdks
        assert "langchain" in sdks

    def test_detect_nested_import(self, python_detector: PythonDetector) -> None:
        code = "from langchain.llms import OpenAI"
        findings = list(python_detector.detect(code, Path("main.py")))

        assert len(findings) >= 1
        sdks = {f.sdk_usage.sdk for f in findings if f.sdk_usage}
        assert "langchain" in sdks

    def test_no_detection_for_unrelated_imports(self, python_detector: PythonDetector) -> None:
        code = """import os
import sys
from pathlib import Path
"""
        findings = list(python_detector.detect(code, Path("main.py")))
        assert len(findings) == 0

    def test_detect_with_line_numbers(self, python_detector: PythonDetector) -> None:
        code = """# comment
import os
import openai  # line 3
"""
        findings = list(python_detector.detect(code, Path("main.py")))

        assert len(findings) == 1
        assert findings[0].line == 3

    def test_file_path_in_finding(self, python_detector: PythonDetector) -> None:
        code = "import openai"
        findings = list(python_detector.detect(code, Path("src/app/main.py")))

        assert findings[0].file_path == "src/app/main.py"

    def test_detect_torch(self, python_detector: PythonDetector) -> None:
        code = "import torch"
        findings = list(python_detector.detect(code, Path("model.py")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "torch"

    def test_detect_tensorflow(self, python_detector: PythonDetector) -> None:
        code = "import tensorflow as tf"
        findings = list(python_detector.detect(code, Path("model.py")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "tensorflow"

    def test_detect_transformers(self, python_detector: PythonDetector) -> None:
        code = "from transformers import AutoModel"
        findings = list(python_detector.detect(code, Path("model.py")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "transformers"


@pytest.fixture
def js_detector() -> JavaScriptDetector:
    return JavaScriptDetector()


class TestJavaScriptDetector:
    def test_supported_extensions(self, js_detector: JavaScriptDetector) -> None:
        assert ".js" in js_detector.extensions
        assert ".ts" in js_detector.extensions
        assert ".jsx" in js_detector.extensions
        assert ".tsx" in js_detector.extensions

    def test_detect_es_import(self, js_detector: JavaScriptDetector) -> None:
        code = 'import OpenAI from "openai";'
        findings = list(js_detector.detect(code, Path("main.js")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "openai"

    def test_detect_es_import_single_quotes(self, js_detector: JavaScriptDetector) -> None:
        code = "import OpenAI from 'openai';"
        findings = list(js_detector.detect(code, Path("main.js")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "openai"

    def test_detect_require(self, js_detector: JavaScriptDetector) -> None:
        code = 'const openai = require("openai");'
        findings = list(js_detector.detect(code, Path("main.js")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "openai"

    def test_detect_scoped_package(self, js_detector: JavaScriptDetector) -> None:
        code = 'import Anthropic from "@anthropic-ai/sdk";'
        findings = list(js_detector.detect(code, Path("main.ts")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "@anthropic-ai/sdk"

    def test_detect_langchain(self, js_detector: JavaScriptDetector) -> None:
        code = 'import { ChatOpenAI } from "langchain/chat_models/openai";'
        findings = list(js_detector.detect(code, Path("main.ts")))

        assert len(findings) >= 1
        sdks = {f.sdk_usage.sdk for f in findings if f.sdk_usage}
        assert "langchain" in sdks

    def test_detect_vercel_ai(self, js_detector: JavaScriptDetector) -> None:
        code = 'import { useChat } from "ai";'
        findings = list(js_detector.detect(code, Path("app.tsx")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "ai"

    def test_no_detection_for_unrelated_imports(self, js_detector: JavaScriptDetector) -> None:
        code = """import React from 'react';
import { useState } from 'react';
const fs = require('fs');
"""
        findings = list(js_detector.detect(code, Path("main.js")))
        assert len(findings) == 0

    def test_detect_with_line_numbers(self, js_detector: JavaScriptDetector) -> None:
        code = """// comment
import React from 'react';
import OpenAI from 'openai';
"""
        findings = list(js_detector.detect(code, Path("main.js")))

        assert len(findings) == 1
        assert findings[0].line == 3


@pytest.fixture
def go_detector() -> GoDetector:
    return GoDetector()


class TestGoDetector:
    def test_supported_extensions(self, go_detector: GoDetector) -> None:
        assert ".go" in go_detector.extensions

    def test_detect_openai_import(self, go_detector: GoDetector) -> None:
        code = 'import "github.com/sashabaranov/go-openai"'
        findings = list(go_detector.detect(code, Path("main.go")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "github.com/sashabaranov/go-openai"

    def test_detect_anthropic_import(self, go_detector: GoDetector) -> None:
        code = 'import anthropic "github.com/anthropics/anthropic-sdk-go"'
        findings = list(go_detector.detect(code, Path("main.go")))

        assert len(findings) == 1
        assert "anthropic-sdk-go" in findings[0].sdk_usage.sdk

    def test_detect_import_block(self, go_detector: GoDetector) -> None:
        code = """import (
    "fmt"
    openai "github.com/sashabaranov/go-openai"
)"""
        findings = list(go_detector.detect(code, Path("main.go")))

        assert len(findings) == 1
        assert "go-openai" in findings[0].sdk_usage.sdk

    def test_no_detection_for_unrelated_imports(self, go_detector: GoDetector) -> None:
        code = """import (
    "fmt"
    "net/http"
    "encoding/json"
)"""
        findings = list(go_detector.detect(code, Path("main.go")))
        assert len(findings) == 0


@pytest.fixture
def rust_detector() -> RustDetector:
    return RustDetector()


class TestRustDetector:
    def test_supported_extensions(self, rust_detector: RustDetector) -> None:
        assert ".rs" in rust_detector.extensions

    def test_detect_use_statement(self, rust_detector: RustDetector) -> None:
        code = "use async_openai::Client;"
        findings = list(rust_detector.detect(code, Path("main.rs")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "async_openai"

    def test_detect_extern_crate(self, rust_detector: RustDetector) -> None:
        code = "extern crate async_openai;"
        findings = list(rust_detector.detect(code, Path("lib.rs")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "async_openai"

    def test_detect_candle(self, rust_detector: RustDetector) -> None:
        code = "use candle_core::Tensor;"
        findings = list(rust_detector.detect(code, Path("model.rs")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "candle_core"

    def test_no_detection_for_unrelated_imports(self, rust_detector: RustDetector) -> None:
        code = """use std::io;
use serde::Serialize;
use tokio::main;
"""
        findings = list(rust_detector.detect(code, Path("main.rs")))
        assert len(findings) == 0


@pytest.fixture
def java_detector() -> JavaDetector:
    return JavaDetector()


class TestJavaDetector:
    def test_supported_extensions(self, java_detector: JavaDetector) -> None:
        assert ".java" in java_detector.extensions
        assert ".kt" in java_detector.extensions

    def test_detect_langchain4j(self, java_detector: JavaDetector) -> None:
        code = "import dev.langchain4j.model.openai.OpenAiChatModel;"
        findings = list(java_detector.detect(code, Path("Main.java")))

        assert len(findings) == 1
        assert "dev.langchain4j" in findings[0].sdk_usage.sdk

    def test_detect_tensorflow(self, java_detector: JavaDetector) -> None:
        code = "import org.tensorflow.Tensor;"
        findings = list(java_detector.detect(code, Path("Model.java")))

        assert len(findings) == 1
        assert "org.tensorflow" in findings[0].sdk_usage.sdk

    def test_no_detection_for_unrelated_imports(self, java_detector: JavaDetector) -> None:
        code = """import java.util.List;
import com.google.gson.Gson;
"""
        findings = list(java_detector.detect(code, Path("Main.java")))
        assert len(findings) == 0


@pytest.fixture
def ruby_detector() -> RubyDetector:
    return RubyDetector()


class TestRubyDetector:
    def test_supported_extensions(self, ruby_detector: RubyDetector) -> None:
        assert ".rb" in ruby_detector.extensions

    def test_detect_ruby_openai(self, ruby_detector: RubyDetector) -> None:
        code = "require 'ruby-openai'"
        findings = list(ruby_detector.detect(code, Path("app.rb")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "ruby-openai"

    def test_detect_openai_path(self, ruby_detector: RubyDetector) -> None:
        code = 'require "openai/client"'
        findings = list(ruby_detector.detect(code, Path("app.rb")))

        assert len(findings) == 1
        assert findings[0].sdk_usage.sdk == "openai"

    def test_no_detection_for_unrelated_requires(self, ruby_detector: RubyDetector) -> None:
        code = """require 'json'
require 'net/http'
"""
        findings = list(ruby_detector.detect(code, Path("app.rb")))
        assert len(findings) == 0
