"""Tests for manifest parsers."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.manifests.cargo import CargoManifestParser
from ai_finder_scanner.manifests.cocoapods import CocoaPodsManifestParser
from ai_finder_scanner.manifests.composer import ComposerManifestParser
from ai_finder_scanner.manifests.gemfile import GemfileManifestParser
from ai_finder_scanner.manifests.gomod import GoModManifestParser
from ai_finder_scanner.manifests.gradle import GradleManifestParser
from ai_finder_scanner.manifests.maven import MavenManifestParser
from ai_finder_scanner.manifests.npm import NpmManifestParser
from ai_finder_scanner.manifests.nuget import NuGetManifestParser
from ai_finder_scanner.manifests.python import PythonManifestParser
from ai_finder_scanner.manifests.swiftpm import SwiftPMManifestParser
from ai_finder_scanner.models import FindingType


@pytest.fixture
def python_parser() -> PythonManifestParser:
    return PythonManifestParser()


class TestPythonManifestParser:
    def test_supported_files(self, python_parser: PythonManifestParser) -> None:
        assert "requirements.txt" in python_parser.manifest_names
        assert "pyproject.toml" in python_parser.manifest_names

    def test_parse_requirements_txt(self, python_parser: PythonManifestParser) -> None:
        content = """openai>=1.0.0
anthropic==0.5.0
langchain
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 3
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "openai" in names
        assert "anthropic" in names
        assert "langchain" in names

    def test_parse_requirements_with_comments(self, python_parser: PythonManifestParser) -> None:
        content = """# AI dependencies
openai>=1.0.0  # OpenAI SDK
# anthropic is not used
torch
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "openai" in names
        assert "torch" in names

    def test_parse_requirements_with_extras(self, python_parser: PythonManifestParser) -> None:
        content = "transformers[torch]>=4.0.0"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "transformers"

    def test_finding_type_is_manifest_dep(self, python_parser: PythonManifestParser) -> None:
        content = "openai>=1.0.0"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].type == FindingType.MANIFEST_DEP

    def test_version_captured(self, python_parser: PythonManifestParser) -> None:
        content = "openai>=1.0.0"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].manifest_dep.version == ">=1.0.0"

    def test_no_version(self, python_parser: PythonManifestParser) -> None:
        content = "openai"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].manifest_dep.version == ""

    def test_ignores_non_ai_packages(self, python_parser: PythonManifestParser) -> None:
        content = """requests>=2.0.0
flask
django
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 0

    def test_line_numbers(self, python_parser: PythonManifestParser) -> None:
        content = """# comment
requests
openai>=1.0.0
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].line == 3


@pytest.fixture
def npm_parser() -> NpmManifestParser:
    return NpmManifestParser()


class TestNpmManifestParser:
    def test_supported_files(self, npm_parser: NpmManifestParser) -> None:
        assert "package.json" in npm_parser.manifest_names

    def test_parse_dependencies(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "openai": "^4.0.0",
        "@anthropic-ai/sdk": "^0.5.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "openai" in names
        assert "@anthropic-ai/sdk" in names

    def test_parse_dev_dependencies(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "devDependencies": {
        "openai": "^4.0.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "openai"

    def test_parse_langchain(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "langchain": "^0.1.0",
        "@langchain/openai": "^0.0.1"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "langchain" in names
        assert "@langchain/openai" in names

    def test_ignores_non_ai_packages(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "react": "^18.0.0",
        "express": "^4.0.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 0

    def test_invalid_json_returns_empty(self, npm_parser: NpmManifestParser) -> None:
        content = "not valid json"
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 0

    def test_version_captured(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "openai": "^4.0.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert findings[0].manifest_dep.version == "^4.0.0"


# ============ NEW MANIFEST PARSER TESTS ============


@pytest.fixture
def cargo_parser() -> CargoManifestParser:
    return CargoManifestParser()


class TestCargoManifestParser:
    def test_supported_files(self, cargo_parser: CargoManifestParser) -> None:
        assert "Cargo.toml" in cargo_parser.manifest_names

    def test_parse_candle(self, cargo_parser: CargoManifestParser) -> None:
        content = """[dependencies]
candle-core = "0.3"
candle-nn = { version = "0.3", features = ["cuda"] }
"""
        findings = list(cargo_parser.parse(content, Path("Cargo.toml")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "candle-core" in names
        assert "candle-nn" in names

    def test_parse_async_openai(self, cargo_parser: CargoManifestParser) -> None:
        content = """[dependencies]
async-openai = "0.18"
"""
        findings = list(cargo_parser.parse(content, Path("Cargo.toml")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "async-openai"

    def test_ignores_non_ai_packages(self, cargo_parser: CargoManifestParser) -> None:
        content = """[dependencies]
tokio = "1.0"
serde = "1.0"
"""
        findings = list(cargo_parser.parse(content, Path("Cargo.toml")))

        assert len(findings) == 0


@pytest.fixture
def gomod_parser() -> GoModManifestParser:
    return GoModManifestParser()


class TestGoModManifestParser:
    def test_supported_files(self, gomod_parser: GoModManifestParser) -> None:
        assert "go.mod" in gomod_parser.manifest_names

    def test_parse_go_openai(self, gomod_parser: GoModManifestParser) -> None:
        content = """module myapp

require (
    github.com/sashabaranov/go-openai v1.17.9
)
"""
        findings = list(gomod_parser.parse(content, Path("go.mod")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "go-openai"

    def test_parse_langchaingo(self, gomod_parser: GoModManifestParser) -> None:
        content = """module myapp

require (
    github.com/tmc/langchaingo v0.1.5
)
"""
        findings = list(gomod_parser.parse(content, Path("go.mod")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "langchaingo"

    def test_ignores_non_ai_packages(self, gomod_parser: GoModManifestParser) -> None:
        content = """module myapp

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/go-redis/redis v6.15.9
)
"""
        findings = list(gomod_parser.parse(content, Path("go.mod")))

        assert len(findings) == 0


@pytest.fixture
def gemfile_parser() -> GemfileManifestParser:
    return GemfileManifestParser()


class TestGemfileManifestParser:
    def test_supported_files(self, gemfile_parser: GemfileManifestParser) -> None:
        assert "Gemfile" in gemfile_parser.manifest_names

    def test_parse_ruby_openai(self, gemfile_parser: GemfileManifestParser) -> None:
        content = """source 'https://rubygems.org'

gem 'ruby-openai', '~> 6.0'
"""
        findings = list(gemfile_parser.parse(content, Path("Gemfile")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "ruby-openai"

    def test_parse_langchainrb(self, gemfile_parser: GemfileManifestParser) -> None:
        content = """gem "langchainrb"
"""
        findings = list(gemfile_parser.parse(content, Path("Gemfile")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "langchainrb"

    def test_ignores_non_ai_packages(self, gemfile_parser: GemfileManifestParser) -> None:
        content = """gem 'rails'
gem 'puma'
gem 'pg'
"""
        findings = list(gemfile_parser.parse(content, Path("Gemfile")))

        assert len(findings) == 0


@pytest.fixture
def maven_parser() -> MavenManifestParser:
    return MavenManifestParser()


class TestMavenManifestParser:
    def test_supported_files(self, maven_parser: MavenManifestParser) -> None:
        assert "pom.xml" in maven_parser.manifest_names

    def test_parse_langchain4j(self, maven_parser: MavenManifestParser) -> None:
        content = """<project>
    <dependencies>
        <dependency>
            <groupId>dev.langchain4j</groupId>
            <artifactId>langchain4j</artifactId>
            <version>0.25.0</version>
        </dependency>
    </dependencies>
</project>
"""
        findings = list(maven_parser.parse(content, Path("pom.xml")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "langchain4j"
        assert findings[0].manifest_dep.version == "0.25.0"

    def test_parse_djl(self, maven_parser: MavenManifestParser) -> None:
        content = """<project>
    <dependencies>
        <dependency>
            <groupId>ai.djl</groupId>
            <artifactId>api</artifactId>
            <version>0.25.0</version>
        </dependency>
    </dependencies>
</project>
"""
        findings = list(maven_parser.parse(content, Path("pom.xml")))

        assert len(findings) == 1

    def test_ignores_non_ai_packages(self, maven_parser: MavenManifestParser) -> None:
        content = """<project>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.0.0</version>
        </dependency>
    </dependencies>
</project>
"""
        findings = list(maven_parser.parse(content, Path("pom.xml")))

        assert len(findings) == 0


@pytest.fixture
def gradle_parser() -> GradleManifestParser:
    return GradleManifestParser()


class TestGradleManifestParser:
    def test_supported_files(self, gradle_parser: GradleManifestParser) -> None:
        assert "build.gradle" in gradle_parser.manifest_names
        assert "build.gradle.kts" in gradle_parser.manifest_names

    def test_parse_langchain4j(self, gradle_parser: GradleManifestParser) -> None:
        content = """dependencies {
    implementation 'dev.langchain4j:langchain4j:0.25.0'
}
"""
        findings = list(gradle_parser.parse(content, Path("build.gradle")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "langchain4j"

    def test_parse_kotlin_dsl(self, gradle_parser: GradleManifestParser) -> None:
        content = """dependencies {
    implementation("ai.djl:api:0.25.0")
}
"""
        findings = list(gradle_parser.parse(content, Path("build.gradle.kts")))

        assert len(findings) == 1

    def test_ignores_non_ai_packages(self, gradle_parser: GradleManifestParser) -> None:
        content = """dependencies {
    implementation 'org.springframework.boot:spring-boot-starter:3.0.0'
}
"""
        findings = list(gradle_parser.parse(content, Path("build.gradle")))

        assert len(findings) == 0


@pytest.fixture
def composer_parser() -> ComposerManifestParser:
    return ComposerManifestParser()


class TestComposerManifestParser:
    def test_supported_files(self, composer_parser: ComposerManifestParser) -> None:
        assert "composer.json" in composer_parser.manifest_names

    def test_parse_openai_php(self, composer_parser: ComposerManifestParser) -> None:
        content = """{
    "require": {
        "openai-php/client": "^0.8"
    }
}"""
        findings = list(composer_parser.parse(content, Path("composer.json")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "client"

    def test_parse_dev_dependencies(self, composer_parser: ComposerManifestParser) -> None:
        content = """{
    "require-dev": {
        "openai-php/client": "^0.8"
    }
}"""
        findings = list(composer_parser.parse(content, Path("composer.json")))

        assert len(findings) == 1

    def test_ignores_non_ai_packages(self, composer_parser: ComposerManifestParser) -> None:
        content = """{
    "require": {
        "laravel/framework": "^10.0",
        "guzzlehttp/guzzle": "^7.0"
    }
}"""
        findings = list(composer_parser.parse(content, Path("composer.json")))

        assert len(findings) == 0

    def test_invalid_json_returns_empty(self, composer_parser: ComposerManifestParser) -> None:
        content = "not valid json"
        findings = list(composer_parser.parse(content, Path("composer.json")))

        assert len(findings) == 0


# ============ ADDITIONAL MANIFEST PARSER TESTS ============


@pytest.fixture
def nuget_parser() -> NuGetManifestParser:
    return NuGetManifestParser()


class TestNuGetManifestParser:
    def test_supported_files(self, nuget_parser: NuGetManifestParser) -> None:
        assert "packages.config" in nuget_parser.manifest_names

    def test_parse_openai(self, nuget_parser: NuGetManifestParser) -> None:
        content = """<Project>
    <ItemGroup>
        <PackageReference Include="OpenAI" Version="1.0.0" />
    </ItemGroup>
</Project>"""
        findings = list(nuget_parser.parse(content, Path("test.csproj")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "OpenAI"

    def test_parse_azure_openai(self, nuget_parser: NuGetManifestParser) -> None:
        content = """<Project>
    <ItemGroup>
        <PackageReference Include="Azure.AI.OpenAI" Version="1.0.0-beta.5" />
    </ItemGroup>
</Project>"""
        findings = list(nuget_parser.parse(content, Path("test.csproj")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "Azure.AI.OpenAI"

    def test_ignores_non_ai_packages(self, nuget_parser: NuGetManifestParser) -> None:
        content = """<Project>
    <ItemGroup>
        <PackageReference Include="Newtonsoft.Json" Version="13.0.0" />
    </ItemGroup>
</Project>"""
        findings = list(nuget_parser.parse(content, Path("test.csproj")))

        assert len(findings) == 0


@pytest.fixture
def swiftpm_parser() -> SwiftPMManifestParser:
    return SwiftPMManifestParser()


class TestSwiftPMManifestParser:
    def test_supported_files(self, swiftpm_parser: SwiftPMManifestParser) -> None:
        assert "Package.swift" in swiftpm_parser.manifest_names

    def test_parse_openai(self, swiftpm_parser: SwiftPMManifestParser) -> None:
        content = """
let package = Package(
    dependencies: [
        .package(url: "https://github.com/MacPaw/OpenAI", from: "0.2.0"),
    ]
)
"""
        findings = list(swiftpm_parser.parse(content, Path("Package.swift")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "OpenAI"

    def test_ignores_non_ai_packages(self, swiftpm_parser: SwiftPMManifestParser) -> None:
        content = """
let package = Package(
    dependencies: [
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.0.0"),
    ]
)
"""
        findings = list(swiftpm_parser.parse(content, Path("Package.swift")))

        assert len(findings) == 0


@pytest.fixture
def cocoapods_parser() -> CocoaPodsManifestParser:
    return CocoaPodsManifestParser()


class TestCocoaPodsManifestParser:
    def test_supported_files(self, cocoapods_parser: CocoaPodsManifestParser) -> None:
        assert "Podfile" in cocoapods_parser.manifest_names

    def test_parse_tflite(self, cocoapods_parser: CocoaPodsManifestParser) -> None:
        content = """platform :ios, '12.0'

target 'MyApp' do
    pod 'TensorFlowLiteSwift', '~> 2.10'
end
"""
        findings = list(cocoapods_parser.parse(content, Path("Podfile")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "TensorFlowLiteSwift"

    def test_parse_mlkit(self, cocoapods_parser: CocoaPodsManifestParser) -> None:
        content = """pod 'GoogleMLKit/TextRecognition'
"""
        findings = list(cocoapods_parser.parse(content, Path("Podfile")))

        assert len(findings) == 1

    def test_ignores_non_ai_packages(self, cocoapods_parser: CocoaPodsManifestParser) -> None:
        content = """pod 'Alamofire'
pod 'SwiftyJSON'
"""
        findings = list(cocoapods_parser.parse(content, Path("Podfile")))

        assert len(findings) == 0
