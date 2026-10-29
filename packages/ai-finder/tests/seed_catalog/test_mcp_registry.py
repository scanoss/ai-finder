"""The MCP Registry importer: what it proposes, and what it refuses."""

from __future__ import annotations

import pytest

from scripts.seed_catalog.mcp_registry import candidate_for, fetch_servers, proposals


def _record(name: str, packages: list[dict], status: str = "active", latest: bool = True):
    return {
        "server": {"name": name, "description": f"{name} server", "packages": packages},
        "_meta": {
            "io.modelcontextprotocol.registry/official": {"status": status, "isLatest": latest}
        },
    }


def test_each_package_type_becomes_a_purl() -> None:
    assert candidate_for({"registryType": "npm", "identifier": "@acme/mcp"}) == (
        "pkg:npm/@acme/mcp",
        ["@acme/mcp"],
    )
    assert candidate_for({"registryType": "pypi", "identifier": "Acme-MCP"}) == (
        "pkg:pypi/acme-mcp",
        ["acme-mcp"],
    )
    assert candidate_for({"registryType": "oci", "identifier": "ghcr.io/acme/mcp:1.2"}) == (
        "pkg:docker/acme/mcp?repository_url=ghcr.io",
        ["ghcr.io/acme/mcp"],
    )
    assert candidate_for({"registryType": "oci", "identifier": "docker.io/acme/mcp"}) == (
        "pkg:docker/acme/mcp",
        ["acme/mcp", "docker.io/acme/mcp"],
    )


def test_out_of_scope_packages_are_not_proposed() -> None:
    assert candidate_for({"registryType": "mcpb", "identifier": "https://x/y.mcpb"}) is None
    assert candidate_for({"registryType": "nuget", "identifier": "Acme.Mcp"}) is None
    # A URL where a package name belongs is not a package.
    assert candidate_for({"registryType": "npm", "identifier": "https://u:pw@h/x.tgz"}) is None


def test_only_active_latest_new_servers() -> None:
    servers = [
        _record("io.acme/live", [{"registryType": "npm", "identifier": "acme-live-mcp"}]),
        _record(
            "io.acme/old", [{"registryType": "npm", "identifier": "acme-old-mcp"}], latest=False
        ),
        _record(
            "io.acme/gone",
            [{"registryType": "npm", "identifier": "acme-gone-mcp"}],
            status="deleted",
        ),
        _record("io.acme/remote", []),
        _record("io.acme/known", [{"registryType": "npm", "identifier": "known-mcp"}]),
    ]
    existing = [{"kind": "mcp_server", "id": "known", "purl": "pkg:npm/known-mcp"}]
    rows = proposals(servers, existing)
    assert [r["purl"] for r in rows] == ["pkg:npm/acme-live-mcp"]
    assert rows[0]["kind"] == "mcp_server" and rows[0]["source"] == "mcp-registry"


def test_a_partial_registry_listing_is_refused() -> None:
    pages = iter([(200, {"servers": [], "metadata": {"nextCursor": "c1"}}), (503, "down")])
    with pytest.raises(RuntimeError, match="partial"):
        fetch_servers(lambda url: next(pages))
    endless = lambda url: (200, {"servers": [], "metadata": {"nextCursor": "again"}})  # noqa: E731
    with pytest.raises(RuntimeError, match="partial"):
        fetch_servers(endless, max_pages=3)


def test_personal_namespaces_only_on_request() -> None:
    servers = [
        _record("com.acme/tool", [{"registryType": "npm", "identifier": "acme-tool-mcp"}]),
        _record("io.github.someone/tool", [{"registryType": "npm", "identifier": "someone-mcp"}]),
    ]
    assert [r["purl"] for r in proposals(servers, [])] == ["pkg:npm/acme-tool-mcp"]
    assert len(proposals(servers, [], include_personal=True)) == 2


def test_a_package_on_another_registry_is_not_proposed() -> None:
    private = {
        "registryType": "npm",
        "identifier": "mcp-server",
        "registryBaseUrl": "https://npm.example.com",
    }
    public = {
        "registryType": "npm",
        "identifier": "mcp-server",
        "registryBaseUrl": "https://registry.npmjs.org/",
    }
    assert candidate_for(private) is None
    assert candidate_for(public) == ("pkg:npm/mcp-server", ["mcp-server"])


def test_pypi_names_are_normalised() -> None:
    assert candidate_for({"registryType": "pypi", "identifier": "My_MCP.Server"}) == (
        "pkg:pypi/my-mcp-server",
        ["my-mcp-server"],
    )


def test_a_200_that_is_not_a_listing_is_refused() -> None:
    pages = iter(
        [(200, {"servers": [], "metadata": {"nextCursor": "c1"}}), (200, {"error": "unavailable"})]
    )
    with pytest.raises(RuntimeError, match="partial"):
        fetch_servers(lambda url: next(pages))


def test_images_whose_names_slug_alike_are_both_proposed() -> None:
    servers = [
        _record("com.acme/a", [{"registryType": "oci", "identifier": "docker.io/acme/server:1"}]),
        _record("com.acme/b", [{"registryType": "oci", "identifier": "ghcr.io/acme/server:1"}]),
    ]
    rows = proposals(servers, [])
    assert len(rows) == 2 and len({r["id"] for r in rows}) == 2


def test_publisher_text_only_on_request() -> None:
    servers = [_record("com.acme/tool", [{"registryType": "npm", "identifier": "acme-tool-mcp"}])]
    (row,) = proposals(servers, [])
    assert row["description"] == "MCP server published to the MCP Registry as com.acme/tool"
    (kept,) = proposals(servers, [], keep_descriptions=True)
    assert kept["description"] == "com.acme/tool server"
