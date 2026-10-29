"""MCP (Model Context Protocol) detection.

Two sources, because an MCP server reaches a project in two ways:

- **Config**: an MCP client config (`.mcp.json`, `claude_desktop_config.json`,
  `.vscode/mcp.json`, ...) names each server and how to launch it. The launch
  command names the package (`npx -y @modelcontextprotocol/server-github`), so
  this is the provenance of a third-party server.
- **Code**: source that builds a server or a client with an MCP SDK, or that
  launches a known server package itself.

Both resolve package names against the KB `mcp_servers` table when a matcher is
given. A server the KB does not know is still reported: the config saying it is
an MCP server is the evidence, the KB only adds the identity.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .detectors.base import BaseDetector
from .models import Finding, FindingType, MCPInfo

logger = logging.getLogger(__name__)

# Keys under which client configs list their servers. `mcpServers` is Claude
# Desktop, Claude Code (.mcp.json), Cursor, Cline and Windsurf; `servers` is VS
# Code's .vscode/mcp.json; `context_servers` is Zed.
_SERVER_KEYS = ("mcpServers", "servers", "context_servers")

# Launchers whose first positional argument is a registry package.
_NPM_LAUNCHERS = frozenset({"npx", "bunx", "pnpx"})
_PYPI_LAUNCHERS = frozenset({"uvx"})
_CONTAINER_LAUNCHERS = frozenset({"docker", "podman"})

# docker/podman run flags that take a value, so the value is not the image.
_CONTAINER_VALUE_FLAGS = frozenset(
    {
        "-e",
        "--env",
        "--env-file",
        "-v",
        "--volume",
        "--name",
        "-p",
        "--publish",
        "--network",
        "--mount",
        "-w",
        "--workdir",
        "-u",
        "--user",
        "--entrypoint",
        "--platform",
        "-l",
        "--label",
    }
)
# uvx/npx flags that take a value.
_LAUNCHER_VALUE_FLAGS = frozenset({"--from", "--with", "-p", "--package", "--python", "--index"})


# What a registry package name may look like. Anything else a launcher is
# handed (a URL, a tarball, a path) is not a registry package and must not
# become a purl: those are also where credentials ride.
_NPM_NAME = re.compile(r"^(@[a-z0-9][\w.\-~]*/)?[a-z0-9][\w.\-~]*$", re.IGNORECASE)
_PYPI_REQ = re.compile(
    r"^(?P<name>[a-z0-9][\w.\-]*)(\[[\w,\-]+\])?\s*"
    r"(?:(?:==|@)\s*(?P<exact>[\w.\-+!]+)|(?P<range>[<>=!~][^;]*))?$",
    re.IGNORECASE,
)
_ARCHIVE_SUFFIXES = (".tgz", ".tar.gz", ".tar", ".zip", ".whl", ".tar.bz2", ".git")
_IMAGE_REPO = re.compile(r"^[a-z0-9][a-z0-9._\-/]*$")
_IMAGE_TAG = re.compile(r"^[\w][\w.\-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
# Exact versions only. A range (`1.x`, `^1.2`, `>=0.6`) or a moving tag
# (`latest`, `next`) is what the launcher resolves at run time, not a version.
_EXACT_VERSION = {
    # SemVer 2.0: prerelease and build metadata both allowed.
    "npm": re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?(?:\+[0-9A-Za-z.\-]+)?$"),
    # PEP 440 release, pre/post/dev, and a local label.
    "pypi": re.compile(
        r"^(?:\d+!)?\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?"
        r"(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?$",
        re.IGNORECASE,
    ),
    "docker": re.compile(r"^v?\d+(?:\.\d+)*(?:[-+_][\w.\-]+)?$"),
}


def _exact(version: str | None, ecosystem: str) -> str | None:
    if not version:
        return None
    if ecosystem == "docker" and _DIGEST.match(version):
        return version
    pattern = _EXACT_VERSION.get(ecosystem)
    return version if pattern and pattern.match(version) else None


def _split_version(spec: str, ecosystem: str) -> tuple[str, str | None] | None:
    """Split a registry spec into (name, exact version), or None if it is not one.

    `pkg@1.2.3` / `@scope/pkg@1.2.3` (npm), `pkg==1.2` / `pkg@1.2` / `pkg>=1`
    (pypi). The version is kept only when it pins one release.
    """
    if (
        "://" in spec
        or spec.startswith((".", "/", "~", "\\"))
        or spec.lower().endswith(_ARCHIVE_SUFFIXES)
        or _TOKEN_RE.fullmatch(spec)
    ):
        return None
    if ecosystem == "pypi":
        m = _PYPI_REQ.match(spec)
        if not m:
            return None
        return m.group("name"), _exact(m.group("exact"), "pypi")
    head, sep, tail = spec.rpartition("@")
    name, version = (head, tail) if sep and head else (spec, None)
    if not _NPM_NAME.match(name):
        return None
    # `pkg@file:../x`, `pkg@github:o/r`, `pkg@npm:other`: not this registry
    # package at a version, so not this package at all.
    if version and (":" in version or "/" in version):
        return None
    return name, _exact(version, "npm")


def _split_image(ref: str) -> tuple[str, str | None] | None:
    """Split a container reference into (registry/repository, tag or digest).

    `repo[:tag][@sha256:...]`. The tag is after the last `:` only when that `:`
    follows the last `/`, so a registry port (`host:5000/acme/mcp`) is not one.
    A digest, when present, is the exact version.
    """
    ref, _, digest = ref.partition("@")
    if digest and not _DIGEST.match(digest):
        return None
    tag: str | None = None
    colon = ref.rfind(":")
    if colon > ref.rfind("/"):
        ref, tag = ref[:colon], ref[colon + 1 :]
        if not _IMAGE_TAG.match(tag):
            return None
    parts = ref.split("/")
    registry_like = len(parts) > 1 and (
        "." in parts[0] or ":" in parts[0] or parts[0] == "localhost"
    )
    repo = "/".join(parts[1:]) if registry_like else ref
    if not repo or not _IMAGE_REPO.match(repo):
        return None
    return ref, digest or _exact(tag, "docker")


def _launch_package(command: str, args: list[str]) -> tuple[str, str, str | None] | None:
    """Return (ecosystem, package, version) a launch command runs, if it names one.

    Only the launcher's own options are read: everything from the first
    positional (the package) or a `--` on belongs to the launched server, and is
    never reinterpreted as a launcher option.
    """
    exe = Path(command).name.lower()
    argv = [a for a in args if isinstance(a, str)]

    if exe in ("npm", "pnpm", "yarn") and argv and argv[0] in ("exec", "dlx", "x"):
        exe, argv = "npx", argv[1:]
    if exe == "pipx" and argv and argv[0] == "run":
        exe, argv = "uvx", argv[1:]

    if exe in _NPM_LAUNCHERS or exe in _PYPI_LAUNCHERS:
        ecosystem = "npm" if exe in _NPM_LAUNCHERS else "pypi"
        # `npx --package pkg bin`, `npx -p pkg bin`, `uvx --from pkg bin`: the
        # flag names the package and the positional is only an executable.
        selectors = ("--package", "-p") if ecosystem == "npm" else ("--from",)
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg == "--":
                return None
            if arg in selectors:
                if i + 1 >= len(argv):
                    return None
                split = _split_version(argv[i + 1], ecosystem)
                return (ecosystem, *split) if split else None
            if arg.startswith("--") and "=" in arg and arg.split("=", 1)[0] in selectors:
                split = _split_version(arg.split("=", 1)[1], ecosystem)
                return (ecosystem, *split) if split else None
            if arg in _LAUNCHER_VALUE_FLAGS:
                i += 2
                continue
            if arg.startswith("-"):
                i += 1
                continue
            split = _split_version(arg, ecosystem)
            return (ecosystem, *split) if split else None
        return None

    if exe in _CONTAINER_LAUNCHERS:
        if not argv or argv[0] != "run":
            return None
        skip = False
        for arg in argv[1:]:
            if skip:
                skip = False
                continue
            if arg == "--":
                # Docker's options end here; the next argument is the image.
                rest = argv[argv.index("--", 1) + 1 :]
                image = _split_image(rest[0]) if rest else None
                return ("docker", *image) if image else None
            if arg in _CONTAINER_VALUE_FLAGS:
                skip = True
                continue
            if arg.startswith("-"):
                continue
            image = _split_image(arg)
            return ("docker", *image) if image else None
        return None

    return None


def _docker_purl(image: str, version: str | None) -> str:
    # pkg:docker/<namespace>/<name>, with a non-Docker-Hub registry carried as
    # repository_url, per the purl spec.
    parts = image.split("/")
    qualifier = ""
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        qualifier = f"?repository_url={parts[0]}"
        parts = parts[1:]
    purl = "pkg:docker/" + "/".join(parts)
    if version:
        purl += f"@{version}"
    return purl + qualifier


def _package_purl(ecosystem: str, name: str, version: str | None) -> str:
    if ecosystem == "docker":
        return _docker_purl(name, version)
    encoded = name.replace("@", "%40", 1) if name.startswith("@") else name
    purl = f"pkg:{ecosystem}/{encoded}"
    return f"{purl}@{version}" if version else purl


# Token shapes that must never become a component name.
_TOKEN_RE = re.compile(r"(?:sk|pk|ghp|gho|ghs|xox[bpas]|glpat|AKIA)[-_A-Za-z0-9]{12,}")
# The same shape inside free text, only where a token can start.
_TOKEN_IN_TEXT = re.compile(r"(?<![\w-])" + _TOKEN_RE.pattern)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][\w .:@/\-]{0,63}$")


def _safe_name(name: str | None) -> str | None:
    """A declared server name, or None if it does not look like a name."""
    if not name or not _SAFE_NAME.match(name) or "://" in name or _TOKEN_IN_TEXT.search(name):
        return None
    return name


def _line_of_key(content: str, key: str) -> int | None:
    m = re.search(r'"' + re.escape(key) + r'"\s*:', content)
    return content[: m.start()].count("\n") + 1 if m else None


def _safe_url(url: str) -> str:
    """Scheme, host and path only. Query strings and userinfo carry tokens."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
    except ValueError:  # an unparseable port: report no URL, keep the server
        return ""
    return f"{parts.scheme}://{host}{parts.path}" if parts.scheme and host else ""


def parse_mcp_config(content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
    """Yield one MCP_SERVER finding per server an MCP client config declares.

    Environment variables and headers are never read into the finding: that is
    where configs keep API keys.

    Args:
        content: Config file content.
        path: File path (relative to scan root).
        matcher: Optional KB Matcher (unscoped), for `match_mcp_identifier`.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", path, e)
        return
    if not isinstance(data, dict):
        return

    servers: dict[str, Any] = {}
    for key in _SERVER_KEYS:
        block = data.get(key)
        if isinstance(block, dict):
            servers.update(block)
    # VS Code user settings nest them under "mcp".
    nested = data.get("mcp")
    if isinstance(nested, dict) and isinstance(nested.get("servers"), dict):
        servers.update(nested["servers"])

    for server_name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        raw_args = spec.get("args")
        args: list[str] = (
            [a for a in raw_args if isinstance(a, str)] if isinstance(raw_args, list) else []
        )
        url = spec.get("url") or spec.get("serverUrl")

        package = purl = version = kb_id = None
        ecosystem: str | None = None
        transport: str | None = None
        how: str | None = None

        if isinstance(command, str) and command:
            transport = "stdio"
            # Never the raw arguments: they carry `-e TOKEN=...`, connection
            # strings with passwords and API keys. The program and the package
            # it runs are the provenance; the rest is configuration.
            how = Path(command).name
            launched = _launch_package(command, args)
            if launched:
                ecosystem, package, version = launched
                purl = _package_purl(ecosystem, package, version)
                how = f"{how} {package}" + (f"@{version}" if version else "")
        elif isinstance(url, str) and url:
            declared = str(spec.get("type") or spec.get("transport") or "").lower()
            transport = "sse" if "sse" in declared else "http"
            how = _safe_url(url) or None

        if matcher is not None and package and ecosystem:
            # Identity comes from the package the launcher installs, in that
            # launcher's registry; the KB adds its id, never a different purl.
            kb = matcher.match_mcp_identifier(package, frozenset({ecosystem}))
            if kb:
                kb_id = kb.id

        yield Finding(
            type=FindingType.MCP_SERVER,
            file_path=str(path),
            confidence=1.0,
            line=_line_of_key(content, server_name),
            mcp_info=MCPInfo(
                name=package or _safe_name(server_name) or "mcp-server",
                role="server",
                source="config",
                package=package,
                purl=purl,
                version=version,
                transport=transport,
                kb_id=kb_id,
                how=how,
            ),
        )


# --- source code -----------------------------------------------------------

_PY_SDK_IMPORT = re.compile(
    r"^\s*(?:from\s+(?P<a>mcp|fastmcp|langchain_mcp_adapters|strands\.tools\.mcp)\b[\w.]*\s+import\b"
    r"|import\s+(?P<b>mcp|fastmcp)\b)",
    re.MULTILINE,
)
# A real import or require of an MCP SDK: an `import ... from` statement at the
# start of a line or after a `;` (so `// import ...` is not one), a bare `import "x"`, or a
# `require("x")` / `import("x")` call. Anchoring beats stripping comments,
# which needs a lexer to tell `//` in a URL string from a comment.
_JS_SDK_IMPORT = re.compile(
    r"""(?:(?:^|;)\s*import\b[^;"'`]*?\bfrom\s*|(?:^|;)\s*import\s*|\brequire\s*\(\s*|\bimport\s*\(\s*)"""
    r"""["'](?:@modelcontextprotocol/(?:sdk|server|client|node|core)|fastmcp)(?:/[^"']*)?["']""",
    re.MULTILINE,
)

# (regex, role, transport). A server pattern's first group, when present, is
# the server's declared name.
_PY_CONSTRUCTS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"\bFastMCP\(\s*(?:name\s*=\s*)?[\"']([^\"']+)[\"']"), "server", None),
    (re.compile(r"\bFastMCP\(\s*\)"), "server", None),
    (re.compile(r"\bServer\(\s*[\"']([^\"']+)[\"']"), "server", None),
    (re.compile(r"\bstdio_client\(|\bStdioServerParameters\("), "client", "stdio"),
    (re.compile(r"\bsse_client\("), "client", "sse"),
    (re.compile(r"\bstreamablehttp_client\("), "client", "http"),
    (re.compile(r"\bClientSession\("), "client", None),
    (re.compile(r"\bMCPClient\("), "client", None),  # strands.tools.mcp
    (re.compile(r"\bMultiServerMCPClient\("), "client", None),  # langchain-mcp-adapters
    (re.compile(r"\bMCPServerStdio\("), "client", "stdio"),  # openai-agents
    (re.compile(r"\bMCPServer(?:Sse|StreamableHttp)\("), "client", "http"),
]
_JS_CONSTRUCTS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"\bnew\s+(?:Mcp)?Server\(\s*\{\s*name\s*:\s*[\"'`]([^\"'`]+)"), "server", None),
    (re.compile(r"\bnew\s+McpServer\("), "server", None),
    (re.compile(r"\bnew\s+StdioClientTransport\("), "client", "stdio"),
    (re.compile(r"\bnew\s+SSEClientTransport\("), "client", "sse"),
    (re.compile(r"\bnew\s+StreamableHTTPClientTransport\("), "client", "http"),
    (re.compile(r"\bnew\s+Client\("), "client", None),
]

# A launch inside code: `command` and a literal `args` list written side by
# side as one pair, in either order, as keyword arguments (`command="npx",
# args=[...]`), object properties (`command: "npx", args: [...]`) or dict
# entries (`"command": "npx", "args": [...]`). Requiring the pair rather than
# searching around the command is what keeps another call's `args`, or an
# `args` that is a variable, from being attributed to this launch.
_LAUNCHERS = r"(npx|bunx|pnpx|npm|pnpm|yarn|uvx|pipx|docker|podman)"
_KEY = r"""["']?{}["']?\s*[=:]\s*"""
# A list of string literals only, read quote by quote so a `[` or `]` inside an
# argument (`"/srv/Reports [2026]"`) is just a character.
# A backslash escapes the next character, so `'/srv/O\\'Brien'` is one string.
_STR = r"""(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\\n]|\\.)*`)"""
_GAP = r"(?:\s|#[^\n]*|//[^\n]*)*"  # whitespace and line comments
_ARGS_LIST = r"\[(" + _GAP + r"(?:" + _STR + _GAP + r",?" + _GAP + r")*)\]"
_SEP = _GAP + "," + _GAP
_CODE_LAUNCH = re.compile(
    _KEY.format("command")
    + r"""["'`]"""
    + _LAUNCHERS
    + r"""["'`]"""
    + _SEP
    + _KEY.format("args")
    + _ARGS_LIST
    + "|"
    + _KEY.format("args")
    + _ARGS_LIST
    + _SEP
    + _KEY.format("command")
    + r"""["'`]"""
    + _LAUNCHERS
    + r"""["'`]"""
)
_CODE_STRING = re.compile(
    r"""(?:"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\\n]|\\.)*)`)"""
)


class MCPDetector(BaseDetector):
    """Detect MCP servers and clients built or launched in source code."""

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

    def detect(self, content: str, path: Path, matcher: Any | None = None) -> Iterator[Finding]:
        """Yield MCP findings for one file.

        Constructs (`Server(`, `new Client(`) only count in a file that imports
        an MCP SDK: they are everyday names. A launched server counts in any
        file whose launch names a package the KB lists as an MCP server, and in
        an MCP-importing file whatever package it names.

        Evidence (`how`) is the construct or the program and package, never the
        source line: lines carry `env={"API_KEY": ...}` and URLs with
        credentials, and an SBOM is passed around.
        """
        is_py = path.suffix.lower() == ".py"
        has_sdk = bool((_PY_SDK_IMPORT if is_py else _JS_SDK_IMPORT).search(content))
        if has_sdk:
            yield from self._constructs(content, path, is_py)
        yield from self._launches(content, path, matcher, require_kb=not has_sdk)

    def _constructs(self, content: str, path: Path, is_py: bool) -> Iterator[Finding]:
        constructs = _PY_CONSTRUCTS if is_py else _JS_CONSTRUCTS
        declared_names: set[str] = set()
        server_lines: set[int] = set()
        client_found = False
        for regex, role, transport in constructs:
            # One client finding per file is the useful grain; the transport
            # patterns come first so that one carries a transport.
            if role == "client" and client_found:
                continue
            for m in regex.finditer(content):
                declared = m.group(1) if regex.groups else None
                line_no = content[: m.start()].count("\n") + 1
                if role == "server":
                    # The unnamed pattern re-matches a named server's line. Track
                    # the declared value, not the sanitised name: two servers
                    # whose names are both replaced are still two servers.
                    if line_no in server_lines or (declared and declared in declared_names):
                        continue
                    if declared:
                        declared_names.add(declared)
                    server_lines.add(line_no)
                name = _safe_name(declared)
                construct = m.group(0).split("(", 1)[0].strip() + "(...)"
                yield Finding(
                    type=FindingType.MCP_SERVER if role == "server" else FindingType.MCP_CLIENT,
                    file_path=str(path),
                    confidence=0.9,
                    line=line_no,
                    mcp_info=MCPInfo(
                        name=name or ("mcp-server" if role == "server" else "mcp-client"),
                        role=role,
                        source="code",
                        transport=transport,
                        how=construct,
                    ),
                )
                if role == "client":
                    client_found = True
                    break

    def _launches(
        self, content: str, path: Path, matcher: Any | None, require_kb: bool
    ) -> Iterator[Finding]:
        """Servers this code launches: the launcher rules a config file gets,
        applied to a `command` / `args` pair (see `_CODE_LAUNCH`). In a file
        without an MCP SDK import, a launch counts only when the KB lists that
        exact package as an MCP server.
        """
        launched: set[tuple[str, str]] = set()
        exact = getattr(matcher, "match_mcp_package", None)
        for lm in _CODE_LAUNCH.finditer(content):
            # Groups: (command, args) in the first order, (args, command) in the second.
            command = lm.group(1) or lm.group(4)
            arg_text = lm.group(2) if lm.group(2) is not None else lm.group(3)
            argv = [
                next(g for g in sm.groups() if g is not None)
                for sm in _CODE_STRING.finditer(arg_text)
            ]
            resolved = _launch_package(command, argv)
            if not resolved:
                continue
            ecosystem, package, version = resolved
            if (ecosystem, package) in launched:
                continue
            kb = exact(package, ecosystem) if exact is not None else None
            if require_kb and kb is None:
                continue
            launched.add((ecosystem, package))
            yield Finding(
                type=FindingType.MCP_SERVER,
                file_path=str(path),
                confidence=0.9,
                line=content[: lm.start()].count("\n") + 1,
                mcp_info=MCPInfo(
                    name=package,
                    role="server",
                    source="code",
                    package=package,
                    purl=_package_purl(ecosystem, package, version),
                    version=version,
                    transport="stdio",
                    kb_id=kb.id if kb else None,
                    how=f"{command} {package}" + (f"@{version}" if version else ""),
                ),
            )
