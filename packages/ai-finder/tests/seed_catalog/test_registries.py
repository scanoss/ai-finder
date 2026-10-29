"""Registry clients, driven by a fake fetcher so no test reaches the network.

The distinction every one of these guards is the same: an answer the registry
gave against an answer it never gave. ``exists=False`` is the registry speaking.
``error`` is the network failing. Collapsing the two is what quietly deletes
rows from a customer's detection set on a bad morning.
"""

from __future__ import annotations

import pytest

from scripts.seed_catalog.registries import POPULARITY_SIGNAL, lookup


def fake(responses: dict[str, tuple[int, object]]):
    """A fetch callable backed by a dict, matching on a substring of the URL."""

    def fetch(url: str) -> tuple[int, object]:
        for fragment, response in responses.items():
            if fragment in url:
                return response
        return 404, None

    return fetch


def test_npm_404_is_a_missing_package_not_an_error():
    facts = lookup("pkg:npm/gone", fake({"registry.npmjs.org": (404, None)}))
    assert facts.exists is False
    assert facts.error is None
    assert facts.usable


def test_npm_500_is_an_error_and_leaves_the_package_presumed_present():
    facts = lookup("pkg:npm/flaky", fake({"registry.npmjs.org": (0, "HTTP 500")}))
    assert facts.exists is True, "a server fault says nothing about the package"
    assert facts.error == "HTTP 500"
    assert not facts.usable


def test_npm_reads_version_licence_deprecation_and_downloads():
    facts = lookup(
        "pkg:npm/@modelcontextprotocol/server-slack",
        fake(
            {
                "registry.npmjs.org": (
                    200,
                    {
                        "dist-tags": {"latest": "2025.4.25"},
                        "versions": {
                            "2025.4.25": {
                                "license": "MIT",
                                "deprecated": "Package no longer supported",
                            }
                        },
                        "repository": {
                            "type": "git",
                            "url": "git+https://github.com/mcp/servers.git",
                        },
                    },
                ),
                "api.npmjs.org/downloads": (200, {"downloads": 374561}),
            }
        ),
    )
    assert facts.version == "2025.4.25"
    assert facts.license == "MIT"
    assert facts.deprecated is True
    assert facts.deprecation_reason == "Package no longer supported"
    assert facts.repository == "mcp/servers"
    assert facts.downloads == 374561


def test_a_failed_downloads_call_costs_a_rank_not_the_row():
    facts = lookup(
        "pkg:npm/openai",
        fake(
            {
                "registry.npmjs.org": (
                    200,
                    {
                        "dist-tags": {"latest": "4.0.0"},
                        "versions": {"4.0.0": {"license": "Apache-2.0"}},
                    },
                ),
                "api.npmjs.org/downloads": (0, "TimeoutError"),
            }
        ),
    )
    assert facts.usable and facts.exists
    assert facts.license == "Apache-2.0"
    assert facts.downloads is None


def test_pypi_translates_a_trove_classifier_into_spdx():
    """The seed speaks SPDX; PyPI classifiers do not.

    Without the translation every Apache package on PyPI reports a licence
    change on every run ("Apache-2.0" -> "Apache Software License"), which both
    buries the real changes and writes the vaguer name into the seed.
    """
    facts = lookup(
        "pkg:pypi/thing",
        fake(
            {
                "pypi.org": (
                    200,
                    {
                        "info": {
                            "version": "1.0",
                            "license": "A" * 500,
                            "classifiers": ["License :: OSI Approved :: Apache Software License"],
                        },
                        "urls": [],
                    },
                )
            }
        ),
    )
    assert facts.license == "Apache-2.0"


def test_pypi_prefers_a_pep_639_expression_over_a_classifier():
    facts = lookup(
        "pkg:pypi/thing",
        fake(
            {
                "pypi.org": (
                    200,
                    {
                        "info": {
                            "version": "1.0",
                            "license_expression": "MIT OR Apache-2.0",
                            "classifiers": ["License :: OSI Approved :: MIT License"],
                        },
                        "urls": [],
                    },
                )
            }
        ),
    )
    assert facts.license == "MIT OR Apache-2.0"


def test_an_untranslatable_classifier_passes_through_so_the_gap_is_visible():
    facts = lookup(
        "pkg:pypi/thing",
        fake(
            {
                "pypi.org": (
                    200,
                    {
                        "info": {
                            "version": "1.0",
                            "classifiers": [
                                "License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)"
                            ],
                        },
                        "urls": [],
                    },
                )
            }
        ),
    )
    assert facts.license == "Eclipse Public License 2.0 (EPL-2.0)"


def test_a_swift_name_with_no_github_repo_is_unverifiable_not_missing():
    """Apple system frameworks are real detections with no repository to find.

    ``apple/coreml`` has no GitHub repo, so a 404 here means the check cannot
    answer. Reading it as "gone" would delete every Apple framework from the
    seed on the first run.
    """
    facts = lookup("pkg:swift/apple/coreml", fake({"api.github.com": (404, None)}))
    assert facts.exists is True
    assert not facts.usable
    assert "no package registry" in facts.error


def test_a_swift_package_that_is_on_github_still_verifies():
    """The negative control: the rule above must not blind the check entirely."""
    facts = lookup(
        "pkg:swift/macpaw/openai",
        fake(
            {
                "api.github.com": (
                    200,
                    {
                        "full_name": "macpaw/OpenAI",
                        "license": {"spdx_id": "MIT"},
                        "stargazers_count": 2500,
                    },
                )
            }
        ),
    )
    assert facts.usable and facts.exists
    assert facts.license == "MIT"
    assert facts.downloads == 2500


def test_pypi_treats_a_yanked_latest_release_as_deprecated():
    facts = lookup(
        "pkg:pypi/thing",
        fake(
            {
                "pypi.org": (
                    200,
                    {"info": {"version": "1.0", "classifiers": []}, "urls": [{"yanked": True}]},
                )
            }
        ),
    )
    assert facts.deprecated is True
    assert facts.exists is True


def test_composer_reports_an_abandoned_package_with_its_replacement():
    facts = lookup(
        "pkg:composer/vendor/pkg",
        fake(
            {
                "https://packagist.org/packages/": (
                    200,
                    {
                        "package": {
                            "abandoned": "other/pkg",
                            "versions": {"1.0.0": {"version": "1.0.0", "license": ["MIT"]}},
                            "downloads": {"total": 1234},
                        }
                    },
                )
            }
        ),
    )
    assert facts.deprecated is True
    assert facts.deprecation_reason == "abandoned: other/pkg"
    assert facts.downloads == 1234


def test_composer_asks_the_host_that_serves_package_metadata():
    # repo.packagist.org/packages/<name>.json is a 404 for every package, so a
    # lookup there reported every Composer SDK as deleted.
    asked: list[str] = []

    def fetch(url: str):
        asked.append(url)
        return 200, {"package": {"versions": {"1.0.0": {"version": "1.0.0", "license": ["MIT"]}}}}

    facts = lookup("pkg:composer/openai-php/client", fetch)
    assert asked == ["https://packagist.org/packages/openai-php/client.json"]
    assert facts.exists is True and facts.license == "MIT"


def test_maven_publishes_no_licence_or_downloads_and_does_not_invent_them():
    facts = lookup(
        "pkg:maven/dev.langchain4j/langchain4j",
        fake({"search.maven.org": (200, {"response": {"docs": [{"latestVersion": "1.2.0"}]}})}),
    )
    assert facts.version == "1.2.0"
    assert facts.license is None
    assert facts.downloads is None


def test_conan_is_reported_unverifiable_rather_than_guessed():
    facts = lookup("pkg:conan/dlib", fake({}))
    assert not facts.usable
    assert "no lookup API" in facts.error


def test_an_unknown_ecosystem_is_an_error_not_a_silent_pass():
    facts = lookup("pkg:cocoapods/Thing", fake({}))
    assert not facts.usable
    assert "no registry client" in facts.error


def test_every_ecosystem_with_a_client_declares_what_it_ranks_on():
    from scripts.seed_catalog.registries import CLIENTS

    assert set(CLIENTS) == set(POPULARITY_SIGNAL)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git+https://github.com/openai/openai-python.git", "openai/openai-python"),
        ("https://github.com/openai/openai-python", "openai/openai-python"),
        ("git://github.com/openai/openai-python.git", "openai/openai-python"),
        ("https://example.com/openai", None),
        (None, None),
    ],
)
def test_github_repo_is_recognised_in_every_url_shape_registries_use(url, expected):
    from scripts.seed_catalog.registries import _github_repo

    assert _github_repo(url) == expected


# -------------------------------------------------------------------------------------------
# found by review; each of these shipped wrong before the fix
# -------------------------------------------------------------------------------------------


def test_a_multi_licence_array_is_reported_ambiguous_not_joined_with_or():
    """RubyGems does not say how the entries in `licenses` combine.

    Taking the first loses half the answer; joining them with OR asserts a
    choice the registry never made. "MIT OR Apache-2.0" and "MIT AND
    Apache-2.0" are different obligations, so neither is guessed.
    """
    from scripts.seed_catalog.registries import AMBIGUOUS_LICENSE, is_spdx_like

    facts = lookup(
        "pkg:gem/thing",
        fake({"rubygems.org": (200, {"version": "1.0", "licenses": ["MIT", "Apache-2.0"]})}),
    )
    assert facts.license == AMBIGUOUS_LICENSE + "MIT, Apache-2.0"
    assert not is_spdx_like(facts.license)


def test_a_single_entry_licence_array_is_read_normally():
    """The negative control: one licence in a list is not ambiguous."""
    facts = lookup(
        "pkg:gem/thing",
        fake({"rubygems.org": (200, {"version": "1.0", "licenses": ["MIT"]})}),
    )
    assert facts.license == "MIT"


def test_cargo_reads_the_licence_of_the_version_it_reports():
    """versions[] is newest first, so versions[0] is a prerelease when one exists."""
    facts = lookup(
        "pkg:cargo/thing",
        fake(
            {
                "crates.io": (
                    200,
                    {
                        "crate": {"max_stable_version": "1.0.0", "downloads": 10},
                        "versions": [
                            {"num": "2.0.0-alpha.1", "license": "GPL-3.0-only", "yanked": True},
                            {"num": "1.0.0", "license": "MIT", "yanked": False},
                        ],
                    },
                )
            }
        ),
    )
    assert facts.version == "1.0.0"
    assert facts.license == "MIT", "the prerelease's licence must not be attached to 1.0.0"
    assert facts.deprecated is False


def test_a_go_module_with_capitals_is_escaped_not_lowercased():
    """proxy.golang.org is case-sensitive: lower-casing 404s a live module."""
    seen = []

    def fetch(url):
        seen.append(url)
        return 200, {"Version": "v1.2.3"}

    lookup("pkg:golang/github.com/Azure/azure-sdk-for-go", fetch)
    assert "github.com/!azure/azure-sdk-for-go" in seen[0]
    assert "/azure/" not in seen[0]


def test_the_ambiguous_bsd_classifier_is_not_resolved_to_a_specific_bsd():
    """ "BSD License" does not say which BSD; guessing could overwrite BSD-2-Clause."""
    from scripts.seed_catalog.registries import is_spdx_like

    facts = lookup(
        "pkg:pypi/thing",
        fake(
            {
                "pypi.org": (
                    200,
                    {
                        "info": {
                            "version": "1.0",
                            "classifiers": ["License :: OSI Approved :: BSD License"],
                        },
                        "urls": [],
                    },
                )
            }
        ),
    )
    assert facts.license == "BSD License"
    assert not is_spdx_like(facts.license), "so a committed BSD-2-Clause survives"
