"""Propose MCP server candidates from the official MCP Registry.

    python -m scripts.seed_catalog.mcp_registry            # report what would be added
    python -m scripts.seed_catalog.mcp_registry --write    # add them to candidates.json

The registry (registry.modelcontextprotocol.io) is where MCP server authors
publish their servers, each with the package that runs it. It is the one source
of MCP servers that says, per server, "this npm / PyPI package / container image
is an MCP server", which is exactly the claim a candidate row makes.

Only servers the registry marks active and latest, and only packages from a
registry the scanner can see a launch from: npm (npx), PyPI (uvx, pipx) and
container images (docker, podman). Remote-only servers have no package, and
`.mcpb` bundles, NuGet and Cargo servers are not launched in a way the scanner
reads. Proposed rows still go through refresh.py, which drops any package its
registry does not have; that check is the reason this writes candidates rather
than seed rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from .catalog import CANDIDATES_PATH
from .registries import Fetcher

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"
SOURCE = "mcp-registry"
MAX_PAGES = 5000  # Oct 2026: well over 41,000 servers, 100 a page

_NPM_NAME = re.compile(r"^(@[a-z0-9][\w.\-~]*/)?[a-z0-9][\w.\-~]*$", re.IGNORECASE)
_PYPI_NAME = re.compile(r"^[a-z0-9][\w.\-]*$", re.IGNORECASE)
_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._\-/:]*$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def fetch_servers(fetch=None, max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
    """Every record, following the cursor. Raises if the registry stops answering
    or the page cap is reached: a partial list would read as a complete one."""
    fetch = fetch or Fetcher(delay=0.05)
    servers: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        # version=latest: one record per server rather than one per release,
        # which is most of the listing (150,000 records for ~41,000 servers).
        query = {"limit": "100", "version": "latest", **({"cursor": cursor} if cursor else {})}
        status, body = fetch(f"{REGISTRY_URL}?{urllib.parse.urlencode(query)}")
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"MCP registry answered {status}; refusing a partial list")
        # A 200 that is not a listing (an error object, a maintenance page)
        # carries no cursor, and reading it as the last page would return the
        # pages so far as if they were everything.
        page, metadata = body.get("servers"), body.get("metadata")
        if not isinstance(page, list) or not isinstance(metadata, dict):
            raise RuntimeError(
                "MCP registry answered 200 without a listing; refusing a partial list"
            )
        servers.extend(page)
        cursor = metadata.get("nextCursor")
        if not cursor:
            return servers
    raise RuntimeError(
        f"MCP registry still paging after {max_pages} pages; refusing a partial list"
    )


def _image_purl(identifier: str) -> tuple[str, list[str]] | None:
    """purl and patterns for a container image reference, without tag or digest."""
    ref = identifier.split("@", 1)[0]
    if ref.rfind(":") > ref.rfind("/"):
        ref = ref[: ref.rfind(":")]
    if not _IMAGE.match(ref):
        return None
    parts = ref.split("/")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        registry, repo = parts[0], "/".join(parts[1:])
    else:
        registry, repo = "docker.io", ref
    if registry == "docker.io":
        if "/" not in repo:
            repo = f"library/{repo}"
        return f"pkg:docker/{repo}", [repo, f"docker.io/{repo}"]
    return f"pkg:docker/{repo}?repository_url={registry}", [f"{registry}/{repo}"]


# The public registry each type resolves against. A package published to a
# different registry is a different package that may share a public name, and
# refresh.py can only verify the public one, so it is not proposed.
_PUBLIC_REGISTRY = {"npm": "https://registry.npmjs.org", "pypi": "https://pypi.org"}


def candidate_for(package: dict[str, Any]) -> tuple[str, list[str]] | None:
    """(purl, patterns) for one registry package entry, or None if out of scope."""
    kind = package.get("registryType")
    identifier = str(package.get("identifier") or "").strip()
    base = str(package.get("registryBaseUrl") or "").rstrip("/")
    if kind in _PUBLIC_REGISTRY and base and base != _PUBLIC_REGISTRY[kind]:
        return None
    if kind == "npm" and _NPM_NAME.match(identifier):
        return f"pkg:npm/{identifier}", [identifier]
    if kind == "pypi" and _PYPI_NAME.match(identifier):
        name = re.sub(r"[-_.]+", "-", identifier).lower()  # PEP 503
        return f"pkg:pypi/{name}", [name]
    if kind == "oci":
        return _image_purl(identifier)
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


# Registry namespaces that name a personal account rather than a domain the
# publisher proved it owns. Sampled Oct 2026: 1 in 100 of these npm packages
# took 1,000+ downloads a month, against 11 in 100 under a verified domain.
PERSONAL_NAMESPACES = ("io.github.", "io.gitlab.")


def proposals(
    servers: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    include_personal: bool = False,
    keep_descriptions: bool = False,
) -> list[dict[str, Any]]:
    """New candidate rows: active, latest, in scope, and not already in the pool."""
    have_purls = {e["purl"] for e in existing}
    have_ids = {(e["kind"], e["id"]) for e in existing}
    out: list[dict[str, Any]] = []
    for record in servers:
        meta = (record.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
        if not meta.get("isLatest") or meta.get("status") != "active":
            continue
        server = record.get("server") or {}
        if not include_personal and str(server.get("name", "")).startswith(PERSONAL_NAMESPACES):
            continue
        # The publisher's own description is their text, not a fact about the
        # package; the row carries only the registry name it was published as.
        # --keep-descriptions copies the text when that is wanted.
        registry_name = _CONTROL.sub(" ", str(server.get("name") or "")).strip()[:120]
        description = (
            _CONTROL.sub(" ", str(server.get("description") or "")).strip()[:200]
            if keep_descriptions
            else ""
        ) or f"MCP server published to the MCP Registry as {registry_name}"
        for package in server.get("packages") or []:
            found = candidate_for(package)
            if not found:
                continue
            purl, patterns = found
            if purl in have_purls:
                continue
            # The whole purl, ecosystem and qualifiers included, plus a short
            # hash: a slug alone maps docker.io/acme/server and
            # ghcr.io/acme/server (or a.b and a-b) to one id, and the second
            # package was skipped as a duplicate.
            digest = hashlib.sha256(purl.encode()).hexdigest()[:8]
            ident = f"{_slug(f'mcpreg-{purl[4:]}')[:70]}-{digest}"
            if ("mcp_server", ident) in have_ids:
                continue
            have_purls.add(purl)
            have_ids.add(("mcp_server", ident))
            out.append(
                {
                    "id": ident,
                    "kind": "mcp_server",
                    "purl": purl,
                    "patterns": patterns,
                    "description": description,
                    "priority": 200,
                    "source": SOURCE,
                    "registry_name": server.get("name"),
                }
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="add proposals to candidates.json")
    parser.add_argument("--from-file", type=Path, help="read a saved registry dump instead")
    parser.add_argument(
        "--include-personal",
        action="store_true",
        help="also propose servers published under a personal GitHub/GitLab namespace",
    )
    parser.add_argument(
        "--keep-descriptions",
        action="store_true",
        help="copy each publisher's description text instead of the registry name only",
    )
    args = parser.parse_args(argv)

    servers = json.loads(args.from_file.read_text()) if args.from_file else fetch_servers()
    document = json.loads(CANDIDATES_PATH.read_text())
    new = proposals(
        servers,
        document["entries"],
        include_personal=args.include_personal,
        keep_descriptions=args.keep_descriptions,
    )
    by_type: dict[str, int] = {}
    for row in new:
        eco = row["purl"][4:].split("/", 1)[0]
        by_type[eco] = by_type.get(eco, 0) + 1
    print(f"registry records {len(servers)}, new MCP server candidates {len(new)} {by_type}")
    if args.write:
        document["entries"].extend(new)
        CANDIDATES_PATH.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {len(new)} candidates to {CANDIDATES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
