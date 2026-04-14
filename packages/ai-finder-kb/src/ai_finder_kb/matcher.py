"""Pattern matching against KB data."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from .database import Database
from .models import MCPMatch, ModelMatch, SDKMatch

logger = logging.getLogger(__name__)

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
)


class Matcher:
    """Match patterns against the knowledge base."""

    def __init__(self, db: Database) -> None:
        """Initialize matcher with database connection.

        Args:
            db: Database instance to query.
        """
        self.db = db

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

    def match_model(self, filename: str) -> ModelMatch | None:
        """Match model filename against known models.

        Uses fuzzy matching on model name. Returns the best match
        (longest model name match) to handle base/fine-tuned variants.

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
