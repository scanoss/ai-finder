"""SBOM output formatters."""

from __future__ import annotations

from .cyclonedx import CycloneDXFormatter
from .json_output import JSONFormatter
from .spdx import SPDX23Formatter
from .spdx3 import SPDX3Formatter

# Backward compatibility alias
SPDXFormatter = SPDX23Formatter


def get_formatter(format: str, spdx_version: str | None = None):
    """Get a formatter instance by format name.

    Args:
        format: Output format ('json', 'cyclonedx', 'spdx').
        spdx_version: SPDX version ('2.3' or '3.0'), required for 'spdx' format.

    Returns:
        Formatter instance.

    Raises:
        ValueError: If format is unknown or spdx_version missing for SPDX.
    """
    if format == "cyclonedx":
        return CycloneDXFormatter()
    elif format == "spdx":
        if spdx_version == "2.3":
            return SPDX23Formatter()
        elif spdx_version == "3.0":
            return SPDX3Formatter()
        else:
            raise ValueError("SPDX format requires --spdx-version (2.3 or 3.0)")
    elif format == "json":
        return JSONFormatter()
    else:
        raise ValueError(f"Unknown format: {format}")


__all__ = [
    "CycloneDXFormatter",
    "JSONFormatter",
    "SPDX23Formatter",
    "SPDX3Formatter",
    "SPDXFormatter",
    "get_formatter",
]
