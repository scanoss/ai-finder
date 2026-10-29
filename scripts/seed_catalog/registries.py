"""Per-ecosystem registry lookups for the seed catalogue.

Each ecosystem answers a different subset of the same four questions: does this
package still exist, what is its latest version, what licence does it carry, and
how popular is it. Only some registries publish a download count, so popularity
is optional by design and :data:`POPULARITY_SIGNAL` records what each ecosystem
actually ranks on. A report that silently mixed npm download counts with GitHub
stars would read as one measurement and be four.

The one distinction every client preserves: a lookup that *failed* is not a
package that is *gone*. A 404 sets ``exists=False``; a timeout, a 500 or a
connection reset sets ``error`` and leaves ``exists`` true, because "I could not
look" is a statement about the network, not about the registry's contents.
Dropping a package from the seed on a transient error would quietly shrink what
every downstream scan can detect.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "ai-finder-seed-catalog/1.0 (+https://github.com/scanoss/ai-finder)"

# What each ecosystem's `downloads` field means, or that it has none. Printed in
# the report so a rank is never read as a count the registry did not publish.
POPULARITY_SIGNAL = {
    "npm": "npm downloads, last 30 days",
    "pypi": "PyPI downloads, last 30 days (pypistats)",
    "cargo": "crates.io downloads, all time",
    "gem": "RubyGems downloads, all time",
    "nuget": "NuGet downloads, all time",
    "composer": "Packagist installs, all time",
    "maven": "none published; ranked by GitHub stars where a repo is known",
    "golang": "none published; ranked by GitHub stars where a repo is known",
    "swift": "GitHub stars",
    "github": "GitHub stars",
    "conan": "none published; ranked by curated order",
    "docker": "none published; ranked by curated order",
}

ECOSYSTEMS = frozenset(POPULARITY_SIGNAL)


@dataclass(frozen=True)
class RegistryFacts:
    """What a registry says about one package, or why it could not say.

    ``exists`` false means the registry answered and does not have it. ``error``
    set means the lookup itself failed and nothing here is to be trusted; the
    caller keeps the committed row rather than treating silence as a deletion.
    """

    exists: bool = True
    version: str | None = None
    license: str | None = None
    deprecated: bool = False
    deprecation_reason: str | None = None
    repository: str | None = None
    downloads: int | None = None
    error: str | None = None

    @property
    def usable(self) -> bool:
        """True when the registry answered, whatever the answer was."""
        return self.error is None


class Fetcher:
    """Minimal JSON fetcher with a polite delay, retries and an on-disk cache.

    Injected rather than imported so the tests never reach the network: every
    client takes the fetch callable as an argument.
    """

    def __init__(
        self,
        delay: float = 0.2,
        timeout: float = 20.0,
        retries: int = 2,
        cache: dict[str, Any] | None = None,
    ) -> None:
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.cache = cache if cache is not None else {}
        self._last_call = 0.0

    def __call__(self, url: str) -> tuple[int, Any]:
        """Return ``(status, parsed_json)``. Status 0 means the call never landed.

        A 404 is returned as a status, not raised: "this package is not here" is
        an answer. Anything that prevented an answer raises through to the caller
        as status 0 with the reason in place of the body.
        """
        if url in self.cache:
            return self.cache[url]

        last_reason = "not attempted"
        for attempt in range(self.retries + 1):
            gap = time.monotonic() - self._last_call
            if gap < self.delay:
                time.sleep(self.delay - gap)
            self._last_call = time.monotonic()

            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    result = (response.status, body)
                    self.cache[url] = result
                    return result
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    result = (404, None)
                    self.cache[url] = result
                    return result
                last_reason = f"HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
            if attempt < self.retries:
                time.sleep(0.5 * (attempt + 1))

        logger.debug("giving up on %s: %s", url, last_reason)
        return 0, last_reason


FetchJson = Callable[[str], tuple[int, Any]]


def split_purl(purl: str) -> tuple[str, str]:
    """Split ``pkg:ECOSYSTEM/NAME`` into its ecosystem and name.

    The name keeps every remaining segment, so scoped npm packages
    (``@scope/pkg``), Maven coordinates (``group/artifact``) and Go module paths
    (``github.com/owner/repo``) all survive intact.

    A trailing ``@version`` is dropped, but only when the ``@`` is not the npm
    scope marker at the start of the name: splitting on the first ``@`` turns
    ``@anthropic-ai/sdk`` into the empty string and loses the package entirely.
    """
    if not purl.startswith("pkg:"):
        raise ValueError(f"not a purl: {purl!r}")
    body = purl[4:].split("?", 1)[0]
    ecosystem, _, name = body.partition("/")
    version_at = name.rfind("@")
    if version_at > 0:
        name = name[:version_at]
    if not ecosystem or not name:
        raise ValueError(f"purl has no ecosystem and name: {purl!r}")
    return ecosystem, name


def _github_repo(url: str | None) -> str | None:
    """``owner/repo`` from any GitHub URL shape, or None when it is not one."""
    if not url:
        return None
    cleaned = url.removeprefix("git+").removesuffix(".git")
    if "github.com" not in cleaned:
        return None
    _, _, tail = cleaned.partition("github.com")
    parts = [p for p in tail.strip(":/").split("/") if p]
    return f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else None


# An SPDX identifier or expression: identifiers joined by OR, AND or WITH. Not a
# validator against the SPDX list — it only separates "this is an identifier"
# from "this is a sentence", which is the distinction the seed needs.
_SPDX_SHAPE = re.compile(r"^[A-Za-z0-9.+-]+(?: (?:OR|AND|WITH) [A-Za-z0-9.+-]+)*$")

# Marks a registry answer that names several licences without saying how they
# combine. Never written to the seed: "MIT OR Apache-2.0" and "MIT AND
# Apache-2.0" are different obligations, and the registry stated neither.
AMBIGUOUS_LICENSE = "several licences, relationship not stated: "


def normalise_license(value: str | None) -> str | None:
    """Tidy a registry's licence string without inventing one.

    The only rewrite is Cargo's historical ``MIT/Apache-2.0`` slash form, which
    means the same as ``MIT OR Apache-2.0`` and is the single most common
    non-SPDX spelling in the catalogue. Everything else is returned as the
    registry wrote it, for :func:`is_spdx_like` to judge.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if "/" in text and " " not in text:
        text = " OR ".join(part for part in text.split("/") if part)
    return text


# Placeholders registries publish in the licence field that have the shape of an
# identifier but carry no licence. Listed rather than pattern-matched: each one
# was seen in a real run, and a cleverer rule would reject real identifiers.
_PLACEHOLDER_LICENSES = frozenset(
    {"non-standard", "unknown", "other", "none", "custom", "proprietary", "see-license"}
)


def is_spdx_like(value: str | None) -> bool:
    """Whether a licence string is an identifier rather than prose or a placeholder.

    ``SEE LICENSE IN LICENSE``, ``Apache 2.0`` and crates.io's ``non-standard``
    are all things registries really publish, and all three are worse than the
    SPDX id already committed to the seed. The first two fail the shape; the
    third has to be named, because it looks exactly like an identifier.
    """
    if not value or value.strip().lower() in _PLACEHOLDER_LICENSES:
        return False
    return bool(_SPDX_SHAPE.match(value))


def _repo_url(value: Any) -> str | None:
    """The URL out of npm's ``repository`` field, which is a string or a dict.

    Not :func:`_spdx`: that looks for ``type`` first, and npm's repository dict
    is ``{"type": "git", "url": ...}``, so it answers "git" for every package.
    """
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        url = value.get("url")
        return url if isinstance(url, str) and url else None
    return None


def _spdx(value: Any) -> str | None:
    """A licence string from the several shapes registries use for it."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _spdx(value.get("type") or value.get("id") or value.get("name"))
    if isinstance(value, list):
        # RubyGems writes ["MIT", "Apache-2.0"] for a dual-licensed gem and its
        # specification does not say how the entries combine. Returning the
        # first loses half the answer; joining them with OR asserts a choice the
        # registry never made, and for a compliance product an invented
        # disjunction is a wrong legal answer, not an untidy one. So the
        # ambiguity is carried out of here intact for a human to settle.
        found = list(dict.fromkeys(text for text in (_spdx(item) for item in value) if text))
        if not found:
            return None
        if len(found) == 1:
            return found[0]
        return AMBIGUOUS_LICENSE + ", ".join(found)
    return None


# -------------------------------------------------------------------------------------------
# one client per ecosystem
# -------------------------------------------------------------------------------------------


def _npm(name: str, fetch: FetchJson) -> RegistryFacts:
    status, body = fetch(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))

    latest = (body.get("dist-tags") or {}).get("latest")
    release = (body.get("versions") or {}).get(latest) or {}
    deprecated = release.get("deprecated")
    facts = RegistryFacts(
        version=latest,
        license=_spdx(release.get("license") or body.get("license")),
        deprecated=bool(deprecated),
        deprecation_reason=deprecated if isinstance(deprecated, str) else None,
        repository=_github_repo(_repo_url(body.get("repository"))),
    )

    # Downloads come from a second endpoint; a failure there costs a rank, not a row.
    status, body = fetch(
        f"https://api.npmjs.org/downloads/point/last-month/{urllib.parse.quote(name, safe='@')}"
    )
    if status == 200 and isinstance(body, dict) and isinstance(body.get("downloads"), int):
        return _with_downloads(facts, body["downloads"])
    return facts


def _pypi(name: str, fetch: FetchJson) -> RegistryFacts:
    status, body = fetch(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))

    info = body.get("info") or {}
    version = info.get("version")
    # A yanked latest release is PyPI's deprecation: the version still resolves
    # but installers refuse it, so a scan matching it reports a dead dependency.
    yanked = any(f.get("yanked") for f in (body.get("urls") or []))
    urls = info.get("project_urls") or {}
    facts = RegistryFacts(
        version=version,
        license=_license_from_classifiers(info),
        deprecated=yanked,
        deprecation_reason="latest release is yanked" if yanked else None,
        repository=_github_repo(
            urls.get("Source")
            or urls.get("Repository")
            or urls.get("Homepage")
            or info.get("home_page")
        ),
    )

    status, body = fetch(f"https://pypistats.org/api/packages/{urllib.parse.quote(name)}/recent")
    if status == 200 and isinstance(body, dict):
        month = (body.get("data") or {}).get("last_month")
        if isinstance(month, int):
            return _with_downloads(facts, month)
    return facts


# Trove classifiers are not SPDX: PyPI says "Apache Software License" where the
# seed says "Apache-2.0". Reporting that as a licence change would bury the real
# ones in 40 lines of noise and, worse, would write the vaguer name into the
# seed, so classifiers are translated rather than copied.
# "License :: OSI Approved :: BSD License" is deliberately absent: it does not
# say which BSD, and guessing BSD-3-Clause would overwrite a correctly committed
# BSD-2-Clause. Left untranslated, it fails is_spdx_like and the committed
# identifier stands.
_TROVE_TO_SPDX = {
    "Apache Software License": "Apache-2.0",
    "MIT License": "MIT",
    "MIT No Attribution License (MIT-0)": "MIT-0",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.0-only",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Affero General Public License v3": "AGPL-3.0-only",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "ISC License (ISCL)": "ISC",
    "The Unlicense (Unlicense)": "Unlicense",
    "Python Software Foundation License": "PSF-2.0",
    "zlib/libpng License": "Zlib",
}


def _license_from_classifiers(info: dict) -> str | None:
    """PyPI's licence as an SPDX identifier where one can be established.

    ``license_expression`` (PEP 639) is already SPDX and wins. Otherwise a Trove
    classifier is translated through :data:`_TROVE_TO_SPDX`; an untranslatable
    classifier is still better than nothing but is returned as-is, so the report
    shows a human that the vocabulary needs a new entry. ``info.license`` is
    often the entire licence text, so it is only used when it is short enough to
    be an identifier rather than a document.
    """
    expression = info.get("license_expression")
    if isinstance(expression, str) and expression.strip():
        return expression.strip()

    for classifier in info.get("classifiers") or []:
        if classifier.startswith("License :: OSI Approved :: "):
            name = classifier.rsplit(" :: ", 1)[-1]
            return _TROVE_TO_SPDX.get(name, name)

    text = info.get("license")
    if isinstance(text, str) and 0 < len(text.strip()) <= 40:
        return text.strip()
    return None


def _cargo(name: str, fetch: FetchJson) -> RegistryFacts:
    status, body = fetch(f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    crate = body.get("crate") or {}
    versions = body.get("versions") or []
    chosen = crate.get("max_stable_version") or crate.get("max_version")
    # The licence and yanked flag must come from the version actually reported.
    # versions[] is newest first, so versions[0] is a prerelease whenever one
    # exists, and reading it would pair the stable version number with a
    # prerelease's licence.
    release = next((v for v in versions if v.get("num") == chosen), None)
    return RegistryFacts(
        version=chosen,
        license=_spdx(release.get("license")) if release else None,
        deprecated=bool(release and release.get("yanked")),
        repository=_github_repo(crate.get("repository")),
        downloads=crate.get("downloads") if isinstance(crate.get("downloads"), int) else None,
    )


def _gem(name: str, fetch: FetchJson) -> RegistryFacts:
    status, body = fetch(f"https://rubygems.org/api/v1/gems/{urllib.parse.quote(name)}.json")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    return RegistryFacts(
        version=body.get("version"),
        license=_spdx(body.get("licenses")),
        repository=_github_repo(body.get("source_code_uri") or body.get("homepage_uri")),
        downloads=body.get("downloads") if isinstance(body.get("downloads"), int) else None,
    )


def _nuget(name: str, fetch: FetchJson) -> RegistryFacts:
    query = urllib.parse.quote(f"packageid:{name.lower()}")
    status, body = fetch(f"https://azuresearch-usnc.nuget.org/query?q={query}&prerelease=false")
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    hits = body.get("data") or []
    if not hits:
        return RegistryFacts(exists=False)
    hit = hits[0]
    return RegistryFacts(
        version=hit.get("version"),
        license=_spdx(hit.get("licenseExpression")),
        repository=_github_repo(hit.get("projectUrl")),
        downloads=hit.get("totalDownloads") if isinstance(hit.get("totalDownloads"), int) else None,
    )


def _composer(name: str, fetch: FetchJson) -> RegistryFacts:
    # packagist.org, not repo.packagist.org: the repo host serves only the
    # Composer v2 metadata (/p2/...) and answers 404 for /packages/ for every
    # package, which read as "deleted" for all of them.
    status, body = fetch(f"https://packagist.org/packages/{name}.json")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    package = body.get("package") or {}
    versions = package.get("versions") or {}
    stable = next(
        (v for k, v in versions.items() if not k.startswith("dev-") and "-" not in k),
        None,
    )
    downloads = (package.get("downloads") or {}).get("total")
    return RegistryFacts(
        version=(stable or {}).get("version"),
        license=_spdx((stable or {}).get("license")),
        deprecated=bool(package.get("abandoned")),
        deprecation_reason=(
            f"abandoned: {package['abandoned']}"
            if isinstance(package.get("abandoned"), str)
            else "abandoned"
            if package.get("abandoned")
            else None
        ),
        repository=_github_repo(package.get("repository")),
        downloads=downloads if isinstance(downloads, int) else None,
    )


def _maven(name: str, fetch: FetchJson) -> RegistryFacts:
    group, _, artifact = name.partition("/")
    if not artifact:
        return RegistryFacts(error=f"maven purl needs group/artifact, got {name!r}")
    query = urllib.parse.quote(f'g:"{group}" AND a:"{artifact}"')
    status, body = fetch(f"https://search.maven.org/solrsearch/select?q={query}&rows=1&wt=json")
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    docs = ((body.get("response") or {}).get("docs")) or []
    if not docs:
        return RegistryFacts(exists=False)
    # Central's search index publishes no licence and no download count, so both
    # stay None here and the ranker falls back to stars.
    return RegistryFacts(version=docs[0].get("latestVersion"))


def _escape_go_module(name: str) -> str:
    """Go proxy escaping: an upper-case letter becomes ``!`` plus its lower case.

    Module paths are case-sensitive and the proxy requires this encoding, so
    lower-casing the path asks for a module that does not exist and gets a 404
    for a package that is perfectly alive.
    """
    return "".join(f"!{c.lower()}" if c.isupper() else c for c in name)


def _golang(name: str, fetch: FetchJson) -> RegistryFacts:
    status, body = fetch(f"https://proxy.golang.org/{_escape_go_module(name)}/@latest")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    return RegistryFacts(version=body.get("Version"), repository=_github_repo(f"https://{name}"))


def _github(name: str, fetch: FetchJson) -> RegistryFacts:
    status, body = fetch(f"https://api.github.com/repos/{name}")
    if status == 404:
        return RegistryFacts(exists=False)
    if status != 200 or not isinstance(body, dict):
        return RegistryFacts(error=str(body))
    return RegistryFacts(
        version=None,
        license=_spdx((body.get("license") or {}).get("spdx_id")),
        deprecated=bool(body.get("archived")),
        deprecation_reason="repository is archived" if body.get("archived") else None,
        repository=body.get("full_name"),
        downloads=body.get("stargazers_count"),
    )


def _swift(name: str, fetch: FetchJson) -> RegistryFacts:
    """Swift has no package registry, so the only check available is GitHub.

    A 404 is therefore reported as *unverifiable*, not as a missing package. Half
    the Swift rows in the seed are Apple system frameworks — ``apple/coreml``,
    ``apple/vision`` — which are real things to detect in Swift source and have
    no repository to find. Treating "no GitHub repo of that name" as "this
    framework is gone" would silently delete them from the seed on the first
    run, which is precisely the kind of quiet shrinkage this tool exists to
    prevent.
    """
    facts = _github(name, fetch)
    if facts.usable and not facts.exists:
        return RegistryFacts(
            error=(
                f"no GitHub repository {name!r} and Swift has no package registry; "
                "cannot be verified automatically"
            )
        )
    return facts


def _conan(name: str, fetch: FetchJson) -> RegistryFacts:
    """Conan Center publishes no machine-readable index we can rely on.

    Reported as unverifiable rather than guessed at: the row is kept, flagged in
    the report, and ranked by its curated order. Claiming a verification that did
    not happen is worse than saying the ecosystem has none.
    """
    return RegistryFacts(error="conan center publishes no lookup API; not verified")


def _docker(name: str, fetch: FetchJson) -> RegistryFacts:
    """Container images: registries other than Docker Hub need a token to read.

    Unverifiable rather than guessed at, the same as Conan: a committed row is
    kept and the report says it was not checked.
    """
    return RegistryFacts(error="container registries publish no anonymous lookup; not verified")


CLIENTS: dict[str, Callable[[str, FetchJson], RegistryFacts]] = {
    "npm": _npm,
    "pypi": _pypi,
    "cargo": _cargo,
    "gem": _gem,
    "nuget": _nuget,
    "composer": _composer,
    "maven": _maven,
    "golang": _golang,
    "github": _github,
    "swift": _swift,
    "conan": _conan,
    "docker": _docker,
}


def _with_downloads(facts: RegistryFacts, downloads: int) -> RegistryFacts:
    """A copy of ``facts`` carrying a download count from a second endpoint."""
    return RegistryFacts(
        exists=facts.exists,
        version=facts.version,
        license=facts.license,
        deprecated=facts.deprecated,
        deprecation_reason=facts.deprecation_reason,
        repository=facts.repository,
        downloads=downloads,
        error=facts.error,
    )


def lookup(purl: str, fetch: FetchJson) -> RegistryFacts:
    """Registry facts for one purl, dispatched on its ecosystem."""
    ecosystem, name = split_purl(purl)
    client = CLIENTS.get(ecosystem)
    if client is None:
        return RegistryFacts(error=f"no registry client for ecosystem {ecosystem!r}")
    return client(name, fetch)


def stars(repo: str, fetch: FetchJson) -> int | None:
    """GitHub stars for ``owner/repo``, or None when the lookup did not answer."""
    status, body = fetch(f"https://api.github.com/repos/{repo}")
    if status == 200 and isinstance(body, dict):
        count = body.get("stargazers_count")
        return count if isinstance(count, int) else None
    return None
