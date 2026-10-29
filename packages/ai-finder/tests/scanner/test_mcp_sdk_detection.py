"""SDK and MCP identification against the KB's identifier lists, end to end.

The KB has always carried SDK and MCP identifiers (several names per package,
like models), but the scanner never handed its matcher to the detectors and
never read an MCP config, so none of it reached the SBOM. These tests use the
real seed JSONs, not hand-written rows, so a seed edit that drops an
identifier fails here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ai_finder_cli.main import main
from ai_finder_kb.database import Database
from ai_finder_kb.matcher import Matcher, purl_ecosystem, purl_name
from ai_finder_scanner.detectors.javascript import JavaScriptDetector
from ai_finder_scanner.detectors.tools import ToolsDetector
from ai_finder_scanner.mcp import MCPDetector, parse_mcp_config
from ai_finder_scanner.models import (
    Finding,
    FindingType,
    ManifestDep,
    MCPInfo,
    ScanResult,
    SDKUsage,
)
from ai_finder_scanner.output.cyclonedx import CycloneDXFormatter
from ai_finder_scanner.output.spdx import SPDX23Formatter
from ai_finder_scanner.output.spdx3 import SPDX3Formatter
from ai_finder_scanner.scanner import Scanner
from click.testing import CliRunner

SEED_DIR = Path(__file__).parents[2] / "src" / "ai_finder_kb" / "seed"


@pytest.fixture
def seed_kb(tmp_path: Path) -> Path:
    """A KB holding the real seed SDK and MCP rows (models left out: slow, unused)."""
    db_path = tmp_path / "kb.db"
    with Database(db_path) as db:
        db.initialize()
        for row in json.loads((SEED_DIR / "sdks.json").read_text()):
            db.execute(
                "INSERT INTO sdks (id, purl, patterns, category, license) VALUES (?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row["purl"],
                    json.dumps(row["patterns"]),
                    row.get("category"),
                    row.get("license"),
                ),
            )
        for row in json.loads((SEED_DIR / "mcp_servers.json").read_text()):
            db.execute(
                "INSERT INTO mcp_servers (id, purl, patterns, description) VALUES (?, ?, ?, ?)",
                (row["id"], row["purl"], json.dumps(row["patterns"]), row.get("description")),
            )
        db.commit()
    return db_path


@pytest.fixture
def matcher(seed_kb: Path):
    db = Database(seed_kb)
    db.connect()
    yield Matcher(db)
    db.close()


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


# --- matcher -----------------------------------------------------------------


class TestIdentifierMatching:
    def test_import_name_resolves_to_its_package(self, matcher) -> None:
        # `import strands` ships as strands-agents; the PyPI package literally
        # named `strands` is an unrelated physics library.
        match = matcher.match_sdk_identifier("strands.agent", frozenset({"pypi"}))
        assert match is not None
        assert match.purl == "pkg:pypi/strands-agents"

    def test_whole_segment_only(self, matcher) -> None:
        pypi = frozenset({"pypi"})
        # Substring matching would answer `openai` for langchain_openai and
        # `torch` for torchvision.
        assert matcher.match_sdk_identifier("langchain_openai", pypi).id != "openai"
        torchvision = matcher.match_sdk_identifier("torchvision", pypi)
        assert torchvision is None or torchvision.id != "torch"
        assert matcher.match_sdk_identifier("torch.nn", pypi).id == "torch"

    def test_ecosystem_scoping(self, matcher) -> None:
        assert matcher.match_sdk_identifier("openai", frozenset({"pypi"})).purl == (
            "pkg:pypi/openai"
        )
        assert matcher.match_sdk_identifier("openai", frozenset({"npm"})).purl == "pkg:npm/openai"

    def test_mcp_sdks_are_catalogued(self, matcher) -> None:
        assert matcher.match_sdk_identifier("mcp.server.fastmcp", frozenset({"pypi"})).purl == (
            "pkg:pypi/mcp"
        )
        js = matcher.match_sdk_identifier("@modelcontextprotocol/sdk/client/index.js", None)
        assert js is not None and js.purl == "pkg:npm/@modelcontextprotocol/sdk"


# --- MCP config --------------------------------------------------------------


class TestMCPConfig:
    def test_each_launcher_names_its_package(self, matcher) -> None:
        config = {
            "mcpServers": {
                "gh": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
                "fetch": {"command": "uvx", "args": ["mcp-server-fetch==0.6.2"]},
                "docker-gh": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "-e",
                        "TOKEN",
                        "ghcr.io/github/github-mcp-server",
                    ],
                },
                "pinned": {"command": "npx", "args": ["@acme/thing@2.1.0"]},
                "floating": {"command": "npx", "args": ["@acme/other@latest"]},
            }
        }
        findings = list(parse_mcp_config(json.dumps(config), Path(".mcp.json"), matcher))
        by_name = {f.mcp_info.name: f.mcp_info for f in findings}

        assert all(f.type == FindingType.MCP_SERVER for f in findings)
        assert by_name["@modelcontextprotocol/server-github"].kb_id == "mcp-github"
        assert by_name["mcp-server-fetch"].purl == "pkg:pypi/mcp-server-fetch@0.6.2"
        # The image, not the value of -e.
        docker = by_name["ghcr.io/github/github-mcp-server"]
        assert docker.kb_id == "github-mcp-server"
        assert docker.purl.startswith("pkg:docker/github/github-mcp-server")
        # Not in the KB, still a server: the config is the evidence.
        assert by_name["@acme/thing"].version == "2.1.0"
        assert by_name["@acme/thing"].kb_id is None
        # A dist-tag is not a version.
        assert by_name["@acme/other"].version is None

    def test_secrets_never_reach_the_finding(self, matcher) -> None:
        config = {
            "servers": {
                "remote": {"type": "http", "url": "https://u:pw@mcp.example.com/v1?token=SEKRET"},
                "local": {"command": "npx", "args": ["x-mcp"], "env": {"API_KEY": "SEKRET"}},
                "db": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-e",
                        "TOKEN=SEKRET",
                        "mcp/postgres",
                        "postgresql://u:SEKRET@db/app",
                        "--api-key=SEKRET",
                    ],
                },
            }
        }
        findings = list(parse_mcp_config(json.dumps(config), Path("mcp.json"), matcher))
        assert len(findings) == 3
        db = next(f.mcp_info for f in findings if f.mcp_info.name == "mcp/postgres")
        assert db.how == "docker mcp/postgres"
        assert "SEKRET" not in repr(findings)
        assert "pw" not in repr([f.mcp_info.how for f in findings])
        remote = next(f.mcp_info for f in findings if f.mcp_info.name == "remote")
        assert remote.how == "https://mcp.example.com/v1"
        assert remote.transport == "http"


# --- MCP in code -------------------------------------------------------------


class TestMCPCode:
    def test_python_server_and_client(self, matcher) -> None:
        src = (
            "from mcp.server.fastmcp import FastMCP\n"
            "from mcp.client.stdio import stdio_client\n"
            'mcp = FastMCP("weather")\n'
            "async def go(p):\n"
            "    async with stdio_client(p) as s: ...\n"
        )
        findings = list(MCPDetector().detect(src, Path("srv.py"), matcher.scoped({"pypi"})))
        servers = [f for f in findings if f.type == FindingType.MCP_SERVER]
        clients = [f for f in findings if f.type == FindingType.MCP_CLIENT]
        assert [s.mcp_info.name for s in servers] == ["weather"]
        assert servers[0].line == 3
        assert len(clients) == 1 and clients[0].mcp_info.transport == "stdio"

    def test_code_evidence_is_redacted(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            'p = StdioServerParameters(command="npx", args=["@modelcontextprotocol/server-github"],'
            ' env={"GITHUB_TOKEN": "ghp_abcdefghijklmnopqrstu"}, url="https://u:pw@h/x?k=1")\n'
        )
        findings = list(MCPDetector().detect(src, Path("c.py"), matcher.scoped({"pypi"})))
        assert findings
        for f in findings:
            assert "ghp_abcdefghijklmnopqrstu" not in f.mcp_info.how
            assert "pw@" not in f.mcp_info.how and "k=1" not in f.mcp_info.how

    def test_constructor_names_need_an_mcp_import(self) -> None:
        # `Server(` and `new Client(` are everyday names.
        src = 'from http.server import Server\nsrv = Server("web")\n'
        assert list(MCPDetector().detect(src, Path("web.py"))) == []

    def test_launched_server_resolved_across_ecosystems(self, matcher) -> None:
        # Python code spawning an npm server.
        src = (
            "from mcp import StdioServerParameters\n"
            'p = StdioServerParameters(command="npx", '
            'args=["-y", "@modelcontextprotocol/server-memory"])\n'
        )
        findings = list(MCPDetector().detect(src, Path("c.py"), matcher.scoped({"pypi"})))
        launched = [f.mcp_info for f in findings if f.mcp_info.kb_id]
        assert [m.kb_id for m in launched] == ["mcp-memory"]
        assert purl_ecosystem(launched[0].purl) == "npm"
        assert purl_name(launched[0].purl) == "@modelcontextprotocol/server-memory"

    def test_typescript_server(self) -> None:
        src = (
            'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
            'const s = new McpServer({ name: "notes", version: "1.0.0" });\n'
        )
        findings = list(MCPDetector().detect(src, Path("s.ts")))
        assert [f.mcp_info.name for f in findings] == ["notes"]


# --- regressions found scanning a real project -------------------------------


class TestRegressions:
    def test_js_import_with_a_dotted_subpath(self) -> None:
        # The MCP SDK is only importable by subpath; `[@\w/-]+` refused the dot
        # and the whole import was missed.
        src = 'import {\n  Client,\n} from "@modelcontextprotocol/sdk/client/index.js";\n'
        findings = list(JavaScriptDetector().detect(src, Path("c.ts")))
        assert [f.sdk_usage.sdk for f in findings] == ["@modelcontextprotocol/sdk"]

    def test_tool_named_by_its_function(self) -> None:
        src = (
            "@tool\ndef search_web(q: str) -> str:\n    ...\n\n"
            "@tool\nasync def fetch(u):\n    ...\n"
        )
        names = [f.tool_info.name for f in ToolsDetector().detect(src, Path("t.py"))]
        assert names == ["search_web", "fetch"]


# --- the customer path: CLI scan to SBOM ---------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    _write(
        root,
        ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "gh": {"command": "npx", "args": ["@modelcontextprotocol/server-github"]}
                }
            }
        ),
    )
    _write(
        root,
        ".vscode/mcp.json",
        json.dumps({"servers": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}}}),
    )
    _write(root, "app/agent.py", "from strands import Agent\nfrom openai import OpenAI\n")
    _write(root, "requirements.txt", "strands-agents>=1.25.0\nopenai==1.60.0\nmcp==1.2.0\n")
    _write(root, "web/package.json", json.dumps({"dependencies": {"openai": "^4.0.0"}}))
    _write(root, "web/index.ts", 'import OpenAI from "openai";\n')
    return root


def _cyclonedx(project: Path, kb: Path) -> dict:
    result = CliRunner().invoke(
        main,
        ["--no-telemetry", "scan", "-q", "--no-enrich", "-f", "cyclonedx"]
        + ["--kb-path", str(kb), str(project)],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


class TestSBOM:
    def test_mcp_servers_from_both_config_locations(self, project: Path, seed_kb: Path) -> None:
        bom = _cyclonedx(project, seed_kb)
        purls = {c.get("purl") for c in bom["components"]}
        assert "pkg:npm/modelcontextprotocol/server-github" in purls
        assert "pkg:pypi/mcp-server-fetch" in purls
        gh = next(c for c in bom["components"] if c["name"].endswith("server-github"))
        props = {p["name"]: p["value"] for p in gh["properties"]}
        assert props["ai-finder:mcp:role"] == "server"
        assert props["ai-finder:mcp:source"] == "config"
        assert gh["evidence"]["occurrences"][0]["location"] == ".mcp.json"

    def test_import_and_manifest_are_one_component_with_both_locations(
        self, project: Path, seed_kb: Path
    ) -> None:
        bom = _cyclonedx(project, seed_kb)
        # Packages only: the agent built with it is its own component.
        strands = [c for c in bom["components"] if "strands" in c.get("purl", "")]
        # One component, named for the package, not the import.
        assert [c["name"] for c in strands] == ["strands-agents"]
        locations = {o["location"] for o in strands[0]["evidence"]["occurrences"]}
        assert locations == {"app/agent.py", "requirements.txt"}
        how = {o.get("additionalContext") for o in strands[0]["evidence"]["occurrences"]}
        assert "from strands import Agent" in how

    def test_same_name_in_two_registries_stays_two(self, project: Path, seed_kb: Path) -> None:
        bom = _cyclonedx(project, seed_kb)
        openai = sorted(c["purl"] for c in bom["components"] if c["name"] == "openai")
        assert openai == ["pkg:npm/openai@4.0.0", "pkg:pypi/openai@1.60.0"]
        refs = [c["bom-ref"] for c in bom["components"]]
        assert len(refs) == len(set(refs))


def test_scanner_without_kb_still_detects_mcp_sdk(tmp_path: Path) -> None:
    # The built-in lists remain the floor when no KB is available.
    _write(tmp_path, "s.py", "from mcp.server.fastmcp import FastMCP\n")
    result = Scanner(detect_licenses=False).scan(tmp_path)
    assert [f.sdk_usage.sdk for f in result.findings if f.sdk_usage] == ["mcp"]
    bom = json.loads(CycloneDXFormatter().format(result))
    (mcp,) = [c for c in bom["components"] if c["name"] == "mcp"]
    assert mcp["purl"] == "pkg:pypi/mcp"
    assert mcp["evidence"]["occurrences"][0] == {
        "location": "s.py",
        "line": 1,
        "additionalContext": "from mcp.server.fastmcp import FastMCP",
    }


# --- review round 1 ------------------------------------------------------------


def _all_text(findings) -> str:
    return repr([f.mcp_info for f in findings])


class TestSecretsNeverExported:
    def test_secret_values_in_code_under_any_key(self, matcher) -> None:
        # Arbitrary values, so no token-shape rule can be what hides them.
        src = (
            "from mcp import StdioServerParameters\n"
            'p = StdioServerParameters(command="node", args=["--password", "swordfish"],'
            ' env={"API_KEY": "swordfish"}, url="https://u:swordfish@h/x?k=swordfish")\n'
        )
        findings = list(MCPDetector().detect(src, Path("c.py"), matcher.scoped({"pypi"})))
        assert findings
        assert "swordfish" not in _all_text(findings)

    def test_secret_shaped_server_name_is_not_a_name(self, matcher) -> None:
        src = 'from fastmcp import FastMCP\napp = FastMCP("sk-abcdefghijklmnop")\n'
        findings = list(MCPDetector().detect(src, Path("a.py"), matcher.scoped({"pypi"})))
        assert [f.mcp_info.name for f in findings] == ["mcp-server"]
        assert "sk-abcdefghijklmnop" not in _all_text(findings)

    def test_url_launch_is_not_a_package(self, matcher) -> None:
        config = {
            "mcpServers": {
                "x": {
                    "command": "npx",
                    "args": ["https://u:SEKRET@example.com/server.tgz?token=PRIVATE"],
                }
            }
        }
        (finding,) = parse_mcp_config(json.dumps(config), Path("m.json"), matcher)
        assert finding.mcp_info.purl is None and finding.mcp_info.package is None
        assert "SEKRET" not in _all_text([finding]) and "PRIVATE" not in _all_text([finding])


class TestLaunchParsing:
    def _one(self, matcher, command: str, args: list[str]):
        config = {"mcpServers": {"s": {"command": command, "args": args}}}
        (finding,) = parse_mcp_config(json.dumps(config), Path("m.json"), matcher)
        return finding.mcp_info

    def test_moving_image_tag_is_not_a_version(self, matcher) -> None:
        info = self._one(matcher, "docker", ["run", "ghcr.io/github/github-mcp-server:latest"])
        assert info.version is None
        assert info.kb_id == "github-mcp-server"
        pinned = self._one(matcher, "docker", ["run", "ghcr.io/github/github-mcp-server:v0.5.0"])
        assert pinned.version == "v0.5.0"

    def test_registry_port_is_not_a_tag(self, matcher) -> None:
        info = self._one(matcher, "docker", ["run", "registry.example:5000/acme/mcp:1.2.3"])
        assert info.package == "registry.example:5000/acme/mcp"
        assert info.version == "1.2.3"
        assert info.purl == "pkg:docker/acme/mcp@1.2.3?repository_url=registry.example:5000"

    def test_npx_package_flag_names_the_package(self, matcher) -> None:
        info = self._one(matcher, "npx", ["--package", "@acme/server@2.1.0", "acme-cli"])
        assert (info.package, info.version) == ("@acme/server", "2.1.0")

    def test_bad_url_port_does_not_stop_the_scan(self, matcher) -> None:
        config = {
            "servers": {
                "bad": {"url": "https://host:bad/mcp"},
                "good": {"command": "uvx", "args": ["mcp-server-fetch"]},
            }
        }
        findings = list(parse_mcp_config(json.dumps(config), Path("m.json"), matcher))
        assert sorted(f.mcp_info.name for f in findings) == ["bad", "mcp-server-fetch"]


class TestCodeScope:
    def test_ordinary_import_is_not_a_launched_server(self, matcher) -> None:
        # An MCP SDK import is present, so the detector runs; the second import
        # is still just an import and must not resolve to PyPI from JS.
        src = (
            'import { Client } from "@modelcontextprotocol/sdk/client/index.js";\n'
            'import fetch from "mcp-server-fetch";\n'
        )
        findings = list(MCPDetector().detect(src, Path("app.js"), matcher.scoped({"npm"})))
        assert all(f.mcp_info.purl is None for f in findings)

    def test_js_constructor_needs_a_real_import(self) -> None:
        src = 'const label = "fastmcp";\nconst client = new Client();\n'
        assert list(MCPDetector().detect(src, Path("a.js"))) == []
        imported = 'import { Client } from "fastmcp";\nconst client = new Client();\n'
        assert [f.type for f in MCPDetector().detect(imported, Path("a.js"))] == [
            FindingType.MCP_CLIENT
        ]


class TestIdentityAcrossFormats:
    @pytest.fixture
    def two_openais(self, tmp_path: Path, seed_kb: Path):
        _write(tmp_path, "a.py", "import openai\n")
        _write(tmp_path, "b.ts", 'import OpenAI from "openai";\n')
        _write(tmp_path, "requirements.txt", "openai==1.60.0\n")
        db = Database(seed_kb)
        db.connect()
        yield Scanner(detect_licenses=False).scan(tmp_path, kb=Matcher(db))
        db.close()

    def test_spdx23_keeps_registries_apart(self, two_openais) -> None:
        doc = json.loads(SPDX23Formatter().format(two_openais))
        openai = [p for p in doc["packages"] if p["name"] == "openai"]
        assert len(openai) == 2

    def test_spdx3_keeps_registries_apart_and_merges_import_with_manifest(
        self, two_openais
    ) -> None:
        graph = json.loads(SPDX3Formatter().format(two_openais))["@graph"]
        openai = [e for e in graph if e.get("name") == "openai"]
        assert len(openai) == 2
        assert len({e["spdxId"] for e in openai}) == 2
        pypi = next(e for e in openai if "pypi" in e.get("software_packageUrl", ""))
        # The manifest's version reached the merged element. (SPDX 3 keeps the
        # specifier, `==1.60.0`, as main always has; that is not this change.)
        assert pypi.get("software_packageVersion", "").endswith("1.60.0")
        assert "a.py" in pypi["software_sourceInfo"]
        assert "requirements.txt" in pypi["software_sourceInfo"]

    def test_mcp_server_and_its_manifest_entry_are_one_component(
        self, tmp_path: Path, seed_kb: Path
    ) -> None:
        _write(
            tmp_path,
            ".mcp.json",
            json.dumps(
                {
                    "mcpServers": {
                        "gh": {"command": "npx", "args": ["@modelcontextprotocol/server-github"]}
                    }
                }
            ),
        )
        _write(
            tmp_path,
            "package.json",
            json.dumps({"dependencies": {"@modelcontextprotocol/server-github": "1.0.0"}}),
        )
        bom = _cyclonedx(tmp_path, seed_kb)
        gh = [c for c in bom["components"] if c["name"] == "@modelcontextprotocol/server-github"]
        assert len(gh) == 1
        props = {p["name"]: p["value"] for p in gh[0]["properties"]}
        assert props["ai-finder:mcp:role"] == "server"
        assert {o["location"] for o in gh[0]["evidence"]["occurrences"]} == {
            ".mcp.json",
            "package.json",
        }


def test_spdx3_does_not_enrich_an_unresolved_import(tmp_path: Path) -> None:
    class RecordingEnricher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def lookup_sdk(self, name):
            self.calls.append(name)
            return None

        def lookup_package(self, name, ecosystem):
            self.calls.append(f"{ecosystem}:{name}")
            return None

    _write(tmp_path, "s.py", "import mcp\n")
    result = Scanner(detect_licenses=False).scan(tmp_path)  # no KB: no purl
    assert [f.sdk_usage.sdk for f in result.findings if f.sdk_usage] == ["mcp"]
    enricher = RecordingEnricher()
    SPDX3Formatter().format(result, enricher=enricher)
    assert enricher.calls == []


# --- review round 2 ------------------------------------------------------------


class TestRound2Launches:
    def _cfg(self, matcher, command: str, args: list[str]):
        config = {"mcpServers": {"s": {"command": command, "args": args}}}
        (finding,) = parse_mcp_config(json.dumps(config), Path("m.json"), matcher)
        return finding.mcp_info

    def test_server_arguments_are_never_launcher_options(self, matcher) -> None:
        info = self._cfg(
            matcher,
            "npx",
            ["@modelcontextprotocol/server-github", "--", "--package", "sk-abcdefghijklmnop"],
        )
        assert info.package == "@modelcontextprotocol/server-github"
        assert "sk-abcdefghijklmnop" not in repr(info)
        # Nothing before `--` names a package: what follows is the server's.
        after = self._cfg(matcher, "npx", ["-y", "--", "--package", "swordfish"])
        assert after.package is None and "swordfish" not in repr(after)

    def test_tarball_is_not_a_package_and_requirement_is(self, matcher) -> None:
        assert self._cfg(matcher, "npx", ["server-1.0.0.tgz"]).package is None
        req = self._cfg(matcher, "uvx", ["mcp-server-fetch>=0.6.2"])
        assert (req.package, req.version) == ("mcp-server-fetch", None)
        pinned = self._cfg(matcher, "uvx", ["mcp-server-fetch==0.6.2"])
        assert pinned.version == "0.6.2"

    def test_a_range_is_not_a_version(self, matcher) -> None:
        info = self._cfg(matcher, "npx", ["@acme/server@1.x"])
        assert (info.package, info.version) == ("@acme/server", None)
        assert self._cfg(matcher, "npx", ["@acme/server@1.2.3"]).version == "1.2.3"

    def test_tag_and_digest_together(self, matcher) -> None:
        digest = "sha256:" + "a" * 64
        info = self._cfg(
            matcher, "docker", ["run", f"ghcr.io/github/github-mcp-server:v0.5.0@{digest}"]
        )
        assert info.kb_id == "github-mcp-server"
        assert info.version == digest


class TestRound2Code:
    def test_args_from_another_construct_are_not_borrowed(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            'server_args = ["@modelcontextprotocol/server-memory"]\n'
            # A plain value, so no token-shape rule is what keeps it out.
            'other = dict(args=["swordfish"])\n'
            'p = StdioServerParameters(command="npx", args=server_args)\n'
        )
        findings = list(MCPDetector().detect(src, Path("c.py"), matcher.scoped({"pypi"})))
        assert findings  # the client construct is still reported
        assert all(f.mcp_info.package is None for f in findings)
        assert "swordfish" not in _all_text(findings)

    def test_known_launch_without_sdk_import(self, matcher) -> None:
        src = (
            "import subprocess\n"
            'spec = {"command": "npx", "args": ["@modelcontextprotocol/server-memory"]}\n'
            'subprocess.run([spec["command"], *spec["args"]])\n'
        )
        findings = list(MCPDetector().detect(src, Path("run.py"), matcher.scoped({"pypi"})))
        assert [f.mcp_info.kb_id for f in findings] == ["mcp-memory"]
        # Without an SDK import an unknown package is not claimed as a server.
        other = src.replace("@modelcontextprotocol/server-memory", "left-pad")
        assert list(MCPDetector().detect(other, Path("run.py"), matcher.scoped({"pypi"}))) == []

    def test_pipx_launch_from_code(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            'p = StdioServerParameters(command="pipx", args=["run", "mcp-server-fetch"])\n'
        )
        findings = list(MCPDetector().detect(src, Path("c.py"), matcher.scoped({"pypi"})))
        assert [f.mcp_info.kb_id for f in findings if f.mcp_info.package] == ["mcp-fetch"]

    def test_same_name_launched_from_two_registries(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            'a = StdioServerParameters(command="npx", args=["fastmcp"])\n'
            'b = StdioServerParameters(command="uvx", args=["fastmcp"])\n'
        )
        findings = list(MCPDetector().detect(src, Path("c.py"), matcher.scoped({"pypi"})))
        ecos = sorted(purl_ecosystem(f.mcp_info.purl) for f in findings if f.mcp_info.purl)
        assert ecos == ["npm", "pypi"]

    def test_commented_import_is_not_an_import(self) -> None:
        src = '// import { Client } from "fastmcp";\nconst client = new Client();\n'
        assert list(MCPDetector().detect(src, Path("a.js"))) == []

    def test_two_servers_with_unusable_names_are_two(self, matcher) -> None:
        src = (
            "from fastmcp import FastMCP\n"
            'weather = FastMCP("weather!")\n'
            'calendar = FastMCP("calendar!")\n'
        )
        findings = list(MCPDetector().detect(src, Path("a.py"), matcher.scoped({"pypi"})))
        assert [f.line for f in findings] == [2, 3]


class TestRound2SPDX3:
    @staticmethod
    def _graph(findings):
        doc = SPDX3Formatter().format(ScanResult(root_path="/", findings=findings))
        return [e for e in json.loads(doc)["@graph"] if e.get("type") == "software_Package"]

    @staticmethod
    def _f(path: str, **kw) -> Finding:
        return Finding(file_path=path, confidence=1.0, **kw)

    def test_an_import_does_not_absorb_every_later_version(self) -> None:
        f = self._f
        graph = self._graph(
            [
                f(
                    "a.py",
                    type=FindingType.SDK_USAGE,
                    sdk_usage=SDKUsage(
                        sdk="openai", import_statement="import openai", purl="pkg:pypi/openai"
                    ),
                ),
                f(
                    "requirements.txt",
                    type=FindingType.MANIFEST_DEP,
                    manifest_dep=ManifestDep("openai", "==1.60.0", "requirements.txt"),
                ),
                f(
                    "old/requirements.txt",
                    type=FindingType.MANIFEST_DEP,
                    manifest_dep=ManifestDep("openai", "==1.61.0", "old/requirements.txt"),
                ),
            ]
        )
        versions = sorted(e["software_packageVersion"] for e in graph if e["name"] == "openai")
        assert versions == ["==1.60.0", "==1.61.0"]

    def test_ids_unique_when_a_local_server_shares_a_package_name(self) -> None:
        f = self._f
        graph = self._graph(
            [
                f(
                    "a.py",
                    type=FindingType.SDK_USAGE,
                    sdk_usage=SDKUsage(
                        sdk="openai", import_statement="import openai", purl="pkg:pypi/openai"
                    ),
                ),
                f(
                    "a.py",
                    type=FindingType.MCP_SERVER,
                    mcp_info=MCPInfo(name="openai", role="server", source="code"),
                ),
            ]
        )
        ids = [e["spdxId"] for e in graph if e["name"] == "openai"]
        assert len(ids) == 2 and len(set(ids)) == 2

    def test_unresolved_import_still_meets_its_manifest_entry(self) -> None:
        f = self._f
        graph = self._graph(
            [
                f(
                    "a.py",
                    type=FindingType.SDK_USAGE,
                    sdk_usage=SDKUsage(sdk="mcp", import_statement="import mcp"),
                ),
                f(
                    "requirements.txt",
                    type=FindingType.MANIFEST_DEP,
                    manifest_dep=ManifestDep("mcp", "", "requirements.txt"),
                ),
            ]
        )
        assert len([e for e in graph if e["name"] == "mcp"]) == 1


# --- review round 3 ------------------------------------------------------------


class TestRound3:
    def _code(self, matcher, src: str, name: str = "c.py", eco: str = "pypi"):
        return list(MCPDetector().detect(src, Path(name), matcher.scoped({eco})))

    def _cfg(self, matcher, argv: list[str]):
        config = {"mcpServers": {"s": {"command": argv[0], "args": argv[1:]}}}
        (finding,) = parse_mcp_config(json.dumps(config), Path("m.json"), matcher)
        return finding.mcp_info

    def test_nested_args_are_not_the_launch_args(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            'p = launch(command="npx", args=server_args,\n'
            '           metadata=dict(args=["swordfish"]))\n'
        )
        assert "swordfish" not in _all_text(self._code(matcher, src))

    def test_separate_assignments_are_not_a_launch(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            'args = ["swordfish"]\n'
            "consume(args)\n"
            'command = "npx"\n'
            "args = server_args\n"
        )
        assert "swordfish" not in _all_text(self._code(matcher, src))

    def test_bracket_inside_a_string_does_not_hide_the_launch(self, matcher) -> None:
        src = (
            "from mcp import StdioServerParameters\n"
            "p = StdioServerParameters(\n"
            '    command="npx", args=["@modelcontextprotocol/server-memory"],\n'
            '    env={"NOTE": "("})\n'
        )
        assert [f.mcp_info.kb_id for f in self._code(matcher, src) if f.mcp_info.kb_id] == [
            "mcp-memory"
        ]

    def test_url_string_before_an_import_on_one_line(self, matcher) -> None:
        src = (
            'const endpoint = "https://example.com"; import { Client } from "fastmcp";\n'
            "const client = new Client();\n"
        )
        kinds = [f.type for f in self._code(matcher, src, "a.js", "npm")]
        assert kinds == [FindingType.MCP_CLIENT]

    def test_full_exact_versions_are_kept(self, matcher) -> None:
        assert self._cfg(matcher, ["npx", "@acme/server@1.2.3-rc.1+build.2"]).version == (
            "1.2.3-rc.1+build.2"
        )
        assert self._cfg(matcher, ["uvx", "mcp-server-fetch==0.6.2+local"]).version == (
            "0.6.2+local"
        )

    def test_docker_terminator_then_image(self, matcher) -> None:
        info = self._cfg(matcher, ["docker", "run", "--", "ghcr.io/github/github-mcp-server"])
        assert info.kb_id == "github-mcp-server"

    def test_non_registry_source_is_not_the_package(self, matcher) -> None:
        assert self._cfg(matcher, ["npx", "@acme/server@file:../local"]).package is None

    def test_token_prefix_inside_a_name_is_not_a_token(self, matcher) -> None:
        info = self._cfg(matcher, ["npx", "@acme/task-management-server"])
        assert info.package == "@acme/task-management-server"

    def test_kb_gate_is_exact_package_identity(self, matcher) -> None:
        near = 'p = dict(command="npx", args=["@modelcontextprotocol/server-memory.evil"])\n'
        assert self._code(matcher, near) == []
        exact = 'p = dict(command="npx", args=["@modelcontextprotocol/server-memory"])\n'
        assert [f.mcp_info.kb_id for f in self._code(matcher, exact)] == ["mcp-memory"]

    def test_first_positional_ends_launcher_options(self, matcher) -> None:
        info = self._cfg(
            matcher, ["npx", "@modelcontextprotocol/server-github", "--package", "swordfish"]
        )
        assert info.package == "@modelcontextprotocol/server-github"
        assert "swordfish" not in repr(info)

    def test_spdx3_unresolved_rust_import_meets_its_cargo_entry(self) -> None:
        findings = [
            Finding(
                file_path="src/main.rs",
                confidence=1.0,
                type=FindingType.SDK_USAGE,
                sdk_usage=SDKUsage(sdk="async-openai", import_statement="use async_openai;"),
            ),
            Finding(
                file_path="Cargo.toml",
                confidence=1.0,
                type=FindingType.MANIFEST_DEP,
                manifest_dep=ManifestDep("async-openai", "0.1", "Cargo.toml"),
            ),
        ]
        doc = SPDX3Formatter().format(ScanResult(root_path="/", findings=findings))
        graph = json.loads(doc)["@graph"]
        assert len([e for e in graph if e.get("name") == "async-openai"]) == 1


def test_launch_pair_with_a_comment_between(matcher) -> None:
    src = (
        "from mcp import StdioServerParameters\n"
        "params = StdioServerParameters(\n"
        '    command="npx",  # Launch the filesystem server\n'
        '    args=["-y", "@modelcontextprotocol/server-filesystem", "/srv"],\n'
        ")\n"
    )
    findings = MCPDetector().detect(src, Path("a.py"), matcher.scoped({"pypi"}))
    assert [f.mcp_info.kb_id for f in findings if f.mcp_info.package] == ["mcp-filesystem"]


def test_launch_args_with_brackets_inside_a_string(matcher) -> None:
    src = (
        "from mcp import StdioServerParameters\n"
        "params = StdioServerParameters(\n"
        '    command="npx",\n'
        '    args=["-y", "@modelcontextprotocol/server-filesystem", "/srv/Reports [2026]"],\n'
        ")\n"
    )
    findings = MCPDetector().detect(src, Path("a.py"), matcher.scoped({"pypi"}))
    assert [f.mcp_info.kb_id for f in findings if f.mcp_info.package] == ["mcp-filesystem"]


def test_sdk_v2_split_packages(matcher) -> None:
    # The official servers import the v2 SDK, split into packages; there is no
    # `@modelcontextprotocol/sdk` import in them at all.
    src = (
        'import { McpServer } from "@modelcontextprotocol/server";\n'
        'const server = new McpServer({ name: "memory-server", version: "0.6.3" });\n'
    )
    assert [f.mcp_info.name for f in MCPDetector().detect(src, Path("index.ts"))] == [
        "memory-server"
    ]
    sdk = matcher.match_sdk_identifier("@modelcontextprotocol/server", frozenset({"npm"}))
    assert sdk is not None and sdk.license == "Apache-2.0"
    # `server-memory` is a server package, not the SDK's `server` package.
    assert (
        matcher.match_sdk_identifier("@modelcontextprotocol/server-memory", frozenset({"npm"}))
        is None
    )


def test_launch_args_with_an_escaped_quote(matcher) -> None:
    src = (
        'import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";\n'
        'const t = new StdioClientTransport({ command: "npx", '
        'args: ["-y", "@modelcontextprotocol/server-filesystem", \'/srv/O\\\'Brien\'] });\n'
    )
    findings = MCPDetector().detect(src, Path("c.ts"), matcher.scoped({"npm"}))
    assert [f.mcp_info.kb_id for f in findings if f.mcp_info.package] == ["mcp-filesystem"]
