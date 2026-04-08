"""JSON output formatter."""

from __future__ import annotations

import json
from dataclasses import asdict

from ..models import ScanResult


class JSONFormatter:
    """Format scan results as JSON."""

    def __init__(self, indent: int | None = None) -> None:
        """Initialize formatter.

        Args:
            indent: JSON indentation level (None for compact).
        """
        self.indent = indent

    def format(self, result: ScanResult) -> str:
        """Format scan result as JSON.

        Args:
            result: Scan result to format.

        Returns:
            JSON string.
        """
        data = asdict(result)

        # Convert enum values to strings
        for finding in data["findings"]:
            finding["type"] = finding["type"].value

        return json.dumps(data, indent=self.indent)
