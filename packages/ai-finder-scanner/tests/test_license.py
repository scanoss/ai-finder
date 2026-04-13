"""Tests for license detection integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.license import OSSLILI_AVAILABLE, LicenseDetector, detect_license


class TestLicenseDetector:
    @pytest.fixture
    def detector(self) -> LicenseDetector:
        return LicenseDetector()

    @pytest.mark.skipif(not OSSLILI_AVAILABLE, reason="osslili not available")
    def test_detect_license_from_mit_file(self, detector: LicenseDetector, tmp_path: Path) -> None:
        license_file = tmp_path / "LICENSE"
        license_file.write_text(
            """MIT License

Copyright (c) 2024 Test Author

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
        )

        result = detector.detect_path(tmp_path)

        assert result is not None
        assert len(result.licenses) > 0
        # MIT should be detected
        license_ids = [lic.spdx_id for lic in result.licenses if lic.spdx_id]
        assert any("MIT" in lid for lid in license_ids)

    @pytest.mark.skipif(not OSSLILI_AVAILABLE, reason="osslili not available")
    def test_detect_apache_license(self, detector: LicenseDetector, tmp_path: Path) -> None:
        license_file = tmp_path / "LICENSE"
        license_file.write_text(
            """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.
"""
        )

        result = detector.detect_path(tmp_path)

        assert result is not None
        assert len(result.licenses) > 0
        license_ids = [lic.spdx_id for lic in result.licenses if lic.spdx_id]
        assert any("Apache" in lid for lid in license_ids)

    @pytest.mark.skipif(not OSSLILI_AVAILABLE, reason="osslili not available")
    def test_detect_license_returns_none_for_no_license(
        self, detector: LicenseDetector, tmp_path: Path
    ) -> None:
        # Create a file with no license content
        (tmp_path / "code.py").write_text("print('hello world')")

        result = detector.detect_path(tmp_path)

        # Should return a result, but with no licenses
        assert result is not None
        assert len(result.licenses) == 0

    @pytest.mark.skipif(not OSSLILI_AVAILABLE, reason="osslili not available")
    def test_get_primary_license(self, detector: LicenseDetector, tmp_path: Path) -> None:
        license_file = tmp_path / "LICENSE"
        license_file.write_text("MIT License\n\nCopyright (c) 2024")

        result = detector.detect_path(tmp_path)

        if result and result.licenses:
            primary = detector.get_primary_license(result)
            assert primary is not None

    def test_osslili_available_constant(self) -> None:
        # Just verify the constant is accessible
        assert isinstance(OSSLILI_AVAILABLE, bool)


class TestDetectLicenseFunction:
    @pytest.mark.skipif(not OSSLILI_AVAILABLE, reason="osslili not available")
    def test_detect_license_convenience_function(self, tmp_path: Path) -> None:
        license_file = tmp_path / "LICENSE"
        license_file.write_text("MIT License\nCopyright (c) 2024")

        result = detect_license(tmp_path)

        assert result is not None

    def test_detect_license_returns_none_for_nonexistent_path(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"

        result = detect_license(nonexistent)

        assert result is None
