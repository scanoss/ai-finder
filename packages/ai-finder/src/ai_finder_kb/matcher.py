"""Pattern matching against KB data."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Iterator

from .database import Database
from .models import MCPMatch, ModelMatch, SDKMatch

logger = logging.getLogger(__name__)


def _as_digest(digest: str | bytes) -> bytes | None:
    """Normalize a SHA-256 to the raw 32 bytes stored in `model_files.h`.

    Accepts 64-char hex (what `hashlib.sha256().hexdigest()` and the seed JSON
    give) or the raw bytes. Returns None for anything that is not a SHA-256, so a
    caller passing a truncated or misalgorithmed digest gets a clean miss rather
    than a silently empty query.
    """
    if isinstance(digest, bytes):
        return digest if len(digest) == 32 else None
    try:
        blob = bytes.fromhex(digest.strip())
    except (ValueError, AttributeError):
        return None
    return blob if len(blob) == 32 else None


# Common model file extensions to strip
MODEL_EXTENSIONS = (
    ".gguf",
    ".safetensors",
    ".bin",
    ".pt",
    ".pth",
    ".onnx",
    ".tflite",
    ".mlmodel",
    ".h5",
    ".keras",
    ".pb",
    ".pkl",
    ".pickle",
    ".msgpack",
    ".params",
    ".pdparams",
    ".pdmodel",
    ".pdopt",
)


# Characters that end one segment of an import path or package name. A pattern
# matches an identifier only on a whole segment, so `openai` matches
# `openai.types` but not `langchain_openai`, and `torch` does not match
# `torchvision`.
_SEGMENT_SEPARATORS = "./:\\"


def purl_ecosystem(purl: str | None) -> str | None:
    """Return the purl type (`pypi`, `npm`, ...) or None for a missing purl."""
    if not purl or not purl.startswith("pkg:"):
        return None
    return purl[4:].split("/", 1)[0].lower() or None


def purl_name(purl: str) -> str:
    """Return the package name a purl names, scope included (`@scope/pkg`)."""
    body = purl[4:].split("/", 1)[1] if "/" in purl[4:] else purl[4:]
    body = body.split("?", 1)[0].split("#", 1)[0]
    # Strip a version, but not the leading @ of an npm scope.
    head, sep, tail = body.rpartition("@")
    if sep and head and "/" not in tail:
        body = head
    return body.replace("%40", "@")


def _normalize_package(name: str, ecosystem: str | None) -> str:
    name = name.lower()
    return re.sub(r"[-_.]+", "-", name) if ecosystem == "pypi" else name


def _segment_match(identifier: str, pattern: str) -> bool:
    if identifier == pattern:
        return True
    return identifier.startswith(pattern) and identifier[len(pattern)] in _SEGMENT_SEPARATORS


class Matcher:
    """Match patterns against the knowledge base."""

    def __init__(self, db: Database) -> None:
        """Initialize matcher with database connection.

        Args:
            db: Database instance to query.
        """
        self.db = db
        # (pattern, ecosystem, row) sorted longest pattern first; loaded once.
        self._sdk_index: list[tuple[str, str | None, SDKMatch]] | None = None
        self._mcp_index: list[tuple[str, str | None, MCPMatch]] | None = None

    def _load_sdk_index(self) -> list[tuple[str, str | None, SDKMatch]]:
        if self._sdk_index is None:
            index: list[tuple[str, str | None, SDKMatch]] = []
            cursor = self.db.execute("SELECT id, purl, patterns, category, license FROM sdks")
            for row in cursor:
                try:
                    patterns = json.loads(row["patterns"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Invalid patterns JSON for SDK %s: %s", row["id"], e)
                    continue
                match = SDKMatch(
                    id=row["id"],
                    purl=row["purl"],
                    category=row["category"],
                    license=row["license"],
                    confidence=1.0,
                )
                eco = purl_ecosystem(row["purl"])
                names = list(patterns)
                if row["purl"]:
                    # The package's own registry name is an identifier too: it
                    # is what a manifest or a launch command names.
                    names.append(purl_name(row["purl"]))
                for pattern in names:
                    if isinstance(pattern, str) and pattern:
                        index.append((pattern.lower(), eco, match))
            index.sort(key=lambda item: -len(item[0]))
            self._sdk_index = index
        return self._sdk_index

    def _load_mcp_index(self) -> list[tuple[str, str | None, MCPMatch]]:
        if self._mcp_index is None:
            index: list[tuple[str, str | None, MCPMatch]] = []
            cursor = self.db.execute("SELECT id, purl, patterns, description FROM mcp_servers")
            for row in cursor:
                try:
                    patterns = json.loads(row["patterns"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Invalid patterns JSON for MCP %s: %s", row["id"], e)
                    continue
                match = MCPMatch(
                    id=row["id"],
                    purl=row["purl"],
                    description=row["description"],
                    confidence=1.0,
                )
                eco = purl_ecosystem(row["purl"])
                names = list(patterns)
                if row["purl"]:
                    names.append(purl_name(row["purl"]))
                for pattern in names:
                    if isinstance(pattern, str) and pattern:
                        index.append((pattern.lower(), eco, match))
            index.sort(key=lambda item: -len(item[0]))
            self._mcp_index = index
        return self._mcp_index

    def match_sdk_identifier(
        self, identifier: str, ecosystems: frozenset[str] | None = None
    ) -> SDKMatch | None:
        """Match an import path or package name against SDK identifiers.

        Unlike `match_sdk`, which looks for a pattern anywhere in a statement,
        this matches whole path segments only and prefers the longest pattern,
        so `langchain_openai` resolves to its own entry rather than to `openai`.

        Args:
            identifier: Import path or package name, e.g. `strands.agent`.
            ecosystems: Purl types to consider, e.g. {"pypi"}. The same name is
                a different package in each registry (`openai` exists on PyPI,
                npm and RubyGems), so a Python import must not resolve to npm.

        Returns:
            SDKMatch for the longest matching pattern, or None.
        """
        ident = identifier.strip().lower()
        if not ident:
            return None
        for pattern, eco, match in self._load_sdk_index():
            if ecosystems is not None and eco not in ecosystems:
                continue
            if _segment_match(ident, pattern):
                return match
        return None

    def match_mcp_identifier(
        self, identifier: str, ecosystems: frozenset[str] | None = None
    ) -> MCPMatch | None:
        """Match a package name or import path against MCP server identifiers.

        Same whole-segment, longest-first rule as `match_sdk_identifier`.
        """
        ident = identifier.strip().lower()
        if not ident:
            return None
        for pattern, eco, match in self._load_mcp_index():
            if ecosystems is not None and eco not in ecosystems:
                continue
            if _segment_match(ident, pattern):
                return match
        return None

    def match_mcp_package(self, name: str, ecosystem: str) -> MCPMatch | None:
        """The MCP server whose registry package is exactly `name` in `ecosystem`."""
        wanted = _normalize_package(name, ecosystem)
        for row_purl, match in ((m.purl, m) for _, _, m in self._load_mcp_index()):
            if purl_ecosystem(row_purl) != ecosystem:
                continue
            if _normalize_package(purl_name(row_purl), ecosystem) == wanted:
                return match
        return None

    def scoped(self, ecosystems: frozenset[str]) -> ScopedMatcher:
        """Return a view of this matcher restricted to some ecosystems."""
        return ScopedMatcher(self, ecosystems)

    def match_sdk(self, text: str) -> SDKMatch | None:
        """Match text against SDK patterns.

        Args:
            text: Import statement or SDK name to match.

        Returns:
            SDKMatch if found, None otherwise.
        """
        cursor = self.db.execute("SELECT id, purl, patterns, category, license FROM sdks")

        text_lower = text.lower()
        for row in cursor:
            try:
                patterns = json.loads(row["patterns"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Invalid patterns JSON for SDK %s: %s", row["id"], e)
                continue

            for pattern in patterns:
                if pattern.lower() in text_lower:
                    return SDKMatch(
                        id=row["id"],
                        purl=row["purl"],
                        category=row["category"],
                        license=row["license"],
                        confidence=1.0,
                    )
        return None

    def match_all_sdks(self, texts: list[str]) -> Iterator[SDKMatch]:
        """Match multiple texts against SDK patterns.

        Args:
            texts: List of import statements or SDK names.

        Yields:
            SDKMatch for each match found.
        """
        seen: set[str] = set()
        for text in texts:
            match = self.match_sdk(text)
            if match and match.id not in seen:
                seen.add(match.id)
                yield match

    def lookup_sdk(self, purl: str) -> SDKMatch | None:
        """Lookup SDK by PURL.

        Args:
            purl: Package URL to lookup.

        Returns:
            SDKMatch if found, None otherwise.
        """
        cursor = self.db.execute(
            "SELECT id, purl, category, license FROM sdks WHERE purl = ?",
            (purl,),
        )
        row = cursor.fetchone()
        if row:
            return SDKMatch(
                id=row["id"],
                purl=row["purl"],
                category=row["category"],
                license=row["license"],
                confidence=1.0,
            )
        return None

    def _normalize_filename(self, filename: str) -> str:
        """Normalize model filename for matching.

        Strips all known extensions and converts to lowercase.

        Args:
            filename: Model filename to normalize.

        Returns:
            Normalized filename.
        """
        name_lower = filename.lower()
        # Strip all known extensions (can be stacked like .Q4_K_M.gguf)
        changed = True
        while changed:
            changed = False
            for ext in MODEL_EXTENSIONS:
                if name_lower.endswith(ext):
                    name_lower = name_lower[: -len(ext)]
                    changed = True
                    break
        return name_lower

    def match_model_by_hash(self, digest: str | bytes) -> ModelMatch | None:
        """Match a model weight file by its content SHA-256.

        This is the only resolution path that works on a generically named shard:
        no substring of `model-00003-of-00026.safetensors` will ever match a
        `models.name`, but its hash is exact.

        Args:
            digest: SHA-256 of the file contents, as 64-char hex or 32 raw bytes.

        Returns:
            ModelMatch if found, None otherwise. Confidence is 1.0 for an
            unambiguous hit and 0.95 when the same bytes are published under more
            than one purl, in which case the earliest-registered purl is chosen —
            the presumed original that was later forked or re-uploaded — with the
            purl itself breaking ties so repeated scans of the same file agree.
        """
        blob = _as_digest(digest)
        if blob is None:
            return None

        try:
            cursor = self.db.execute(
                "SELECT m.purl, m.name, m.organization, m.architecture, m.format, "
                "m.parameter_count, m.license "
                "FROM model_files f JOIN models m ON m.id = f.model_id "
                "WHERE f.h = ? GROUP BY m.purl "
                # Same pick rule as KBEnricher.lookup_model_by_hash: earliest
                # registration wins, dated beats undated, purl breaks ties.
                # Two implementations of one lookup must not disagree on
                # which purl a hash resolves to.
                "ORDER BY (m.repo_created_at IS NULL), m.repo_created_at, m.purl",
                (blob,),
            )
            rows = cursor.fetchall()
        except sqlite3.Error as e:
            # A pre-v3 KB has no model_files table. Not an error: the caller falls
            # back to filename matching.
            logger.debug("model_files lookup failed: %s", e)
            return None

        if not rows:
            return None

        row = rows[0]
        return ModelMatch(
            purl=row["purl"],
            name=row["name"],
            organization=row["organization"],
            architecture=row["architecture"],
            format=row["format"],
            parameter_count=row["parameter_count"],
            license=row["license"],
            confidence=1.0 if len(rows) == 1 else 0.95,
        )

    def match_model(self, filename: str) -> ModelMatch | None:
        """Match model filename against known models.

        Uses fuzzy matching on model name. Returns the best match
        (longest model name match) to handle base/fine-tuned variants.

        Prefer `match_model_by_hash` when the file contents are available: this
        cannot identify a generically named shard, and 57% of real weight-file
        basenames are generic.

        Args:
            filename: Model filename to match.

        Returns:
            ModelMatch if found, None otherwise.
        """
        name_lower = self._normalize_filename(filename)

        # Query with ORDER BY name length DESC to prefer longer (more specific) matches
        cursor = self.db.execute(
            "SELECT purl, name, organization, architecture, format, "
            "parameter_count, license FROM models ORDER BY length(name) DESC"
        )

        for row in cursor:
            model_name_lower = row["name"].lower()
            # Check if model name is contained in filename
            if model_name_lower in name_lower or name_lower in model_name_lower:
                return ModelMatch(
                    purl=row["purl"],
                    name=row["name"],
                    organization=row["organization"],
                    architecture=row["architecture"],
                    format=row["format"],
                    parameter_count=row["parameter_count"],
                    license=row["license"],
                    confidence=0.9,
                )
        return None

    def lookup_model(self, purl: str) -> ModelMatch | None:
        """Lookup model by PURL.

        Args:
            purl: Package URL to lookup.

        Returns:
            ModelMatch if found, None otherwise.
        """
        cursor = self.db.execute(
            "SELECT purl, name, organization, architecture, format, "
            "parameter_count, license FROM models WHERE purl = ?",
            (purl,),
        )
        row = cursor.fetchone()
        if row:
            return ModelMatch(
                purl=row["purl"],
                name=row["name"],
                organization=row["organization"],
                architecture=row["architecture"],
                format=row["format"],
                parameter_count=row["parameter_count"],
                license=row["license"],
                confidence=1.0,
            )
        return None

    def match_mcp(self, text: str) -> MCPMatch | None:
        """Match text against MCP server patterns.

        Args:
            text: Import or require statement to match.

        Returns:
            MCPMatch if found, None otherwise.
        """
        cursor = self.db.execute("SELECT id, purl, patterns, description FROM mcp_servers")

        text_lower = text.lower()
        for row in cursor:
            try:
                patterns = json.loads(row["patterns"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Invalid patterns JSON for MCP %s: %s", row["id"], e)
                continue

            for pattern in patterns:
                if pattern.lower() in text_lower:
                    return MCPMatch(
                        id=row["id"],
                        purl=row["purl"],
                        description=row["description"],
                        confidence=1.0,
                    )
        return None

    def lookup_mcp(self, purl: str) -> MCPMatch | None:
        """Lookup MCP server by PURL.

        Args:
            purl: Package URL to lookup.

        Returns:
            MCPMatch if found, None otherwise.
        """
        cursor = self.db.execute(
            "SELECT id, purl, description FROM mcp_servers WHERE purl = ?",
            (purl,),
        )
        row = cursor.fetchone()
        if row:
            return MCPMatch(
                id=row["id"],
                purl=row["purl"],
                description=row["description"],
                confidence=1.0,
            )
        return None


class ScopedMatcher:
    """A Matcher restricted to the ecosystems one language can import from.

    Detectors call `match_sdk(name)` with a bare import path; this answers it
    with whole-segment matching inside the right registries only.
    """

    def __init__(self, matcher: Matcher, ecosystems: frozenset[str]) -> None:
        self._matcher = matcher
        self.ecosystems = ecosystems

    def match_sdk(self, text: str) -> SDKMatch | None:
        return self._matcher.match_sdk_identifier(text, self.ecosystems)

    def match_mcp(self, text: str) -> MCPMatch | None:
        return self._matcher.match_mcp_identifier(text, self.ecosystems)

    def match_mcp_package(self, name: str, ecosystem: str) -> MCPMatch | None:
        """The KB MCP server that IS this registry package, or None.

        Exact package identity: a launched package is a package, not an import
        path, so `@modelcontextprotocol/server-memory.evil` is not
        `@modelcontextprotocol/server-memory`. Code in one language routinely
        launches a server published in another, so the registry comes from the
        launcher, not from the file.
        """
        return self._matcher.match_mcp_package(name, ecosystem)
