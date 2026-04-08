"""License detection using osslili."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import osslili, gracefully degrade if unavailable
try:
    from osslili import (  # type: ignore[import-untyped]
        DetectedLicense,
        DetectionResult,
        LicenseCopyrightDetector,
    )

    OSSLILI_AVAILABLE = True
except ImportError:
    OSSLILI_AVAILABLE = False

    # Placeholders when osslili not available
    class DetectedLicense:  # type: ignore[no-redef]
        """Placeholder for DetectedLicense when osslili unavailable."""

        pass

    class DetectionResult:  # type: ignore[no-redef]
        """Placeholder for DetectionResult when osslili unavailable."""

        licenses: list[object] = []

        def get_primary_license(self) -> None:
            return None

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

    def detect_path(self, path: Path) -> DetectionResult | None:
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

    def detect_file(self, file_path: Path) -> DetectionResult | None:
        """Detect licenses in a single file.

        Args:
            file_path: Path to file to scan.

        Returns:
            DetectionResult with licenses found, or None if unavailable/error.
        """
        return self.detect_path(file_path)

    def get_primary_license(self, result: DetectionResult) -> DetectedLicense | None:
        """Get the primary (highest confidence) license from a result.

        Args:
            result: DetectionResult from detect_path/detect_file.

        Returns:
            DetectedLicense with highest confidence, or None if no licenses.
        """
        if not result or not result.licenses:
            return None

        return result.get_primary_license()


def detect_license(path: Path) -> DetectionResult | None:
    """Convenience function to detect licenses in a path.

    Args:
        path: Path to scan for licenses.

    Returns:
        DetectionResult with licenses found, or None if unavailable/error.
    """
    detector = LicenseDetector()
    return detector.detect_path(path)
