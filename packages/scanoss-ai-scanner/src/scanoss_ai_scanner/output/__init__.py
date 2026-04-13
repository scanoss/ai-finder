"""SBOM output formatters."""

from __future__ import annotations

from .cyclonedx import CycloneDXFormatter
from .json_output import JSONFormatter
from .spdx import SPDX23Formatter
from .spdx3 import SPDX3Formatter

# Backward compatibility alias
SPDXFormatter = SPDX23Formatter

__all__ = ["CycloneDXFormatter", "JSONFormatter", "SPDX23Formatter", "SPDXFormatter", "SPDX3Formatter"]
