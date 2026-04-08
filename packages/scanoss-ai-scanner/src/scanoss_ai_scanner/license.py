"""License detection using osslili."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import osslili, gracefully degrade if unavailable
try:
    from osslili import LicenseCopyrightDetector

    OSSLILI_AVAILABLE = True
except (ImportError, TypeError):
    # ImportError: osslili not installed
    # TypeError: Python 3.8 compatibility issues with osslili's type hints
    OSSLILI_AVAILABLE = False
    LicenseCopyrightDetector = None


class LicenseDetector:
    """Wrapper around osslili for license detection."""

    def __init__(self) -> None:
        """Initialize the license detector."""
        if OSSLILI_AVAILABLE:
            self._detector = LicenseCopyrightDetector()
        else:
            self._detector = None
            logger.warning("osslili not available, license detection disabled")

    @property
    def available(self) -> bool:
        """Check if license detection is available."""
        return OSSLILI_AVAILABLE and self._detector is not None

    def detect_path(self, path: Path) -> Any:
        """Detect licenses in a path (file or directory).

        Args:
            path: Path to scan for licenses.

        Returns:
            DetectionResult with licenses found, or None if unavailable/error.
        """
        if not self.available:
            return None

        if not path.exists():
            return None

        try:
            return self._detector.process_local_path(str(path), extract_archives=False)
        except Exception as e:
            logger.debug("License detection failed for %s: %s", path, e)
            return None

    def detect_file(self, file_path: Path) -> Any:
        """Detect licenses in a single file.

        Args:
            file_path: Path to file to scan.

        Returns:
            DetectionResult with licenses found, or None if unavailable/error.
        """
        return self.detect_path(file_path)

    def get_primary_license(self, result: Any) -> Any:
        """Get the primary (highest confidence) license from a result.

        Args:
            result: DetectionResult from detect_path/detect_file.

        Returns:
            DetectedLicense with highest confidence, or None if no licenses.
        """
        if not result or not result.licenses:
            return None

        return result.get_primary_license()


def detect_license(path: Path) -> Any:
    """Convenience function to detect licenses in a path.

    Args:
        path: Path to scan for licenses.

    Returns:
        DetectionResult with licenses found, or None if unavailable/error.
    """
    detector = LicenseDetector()
    return detector.detect_path(path)
