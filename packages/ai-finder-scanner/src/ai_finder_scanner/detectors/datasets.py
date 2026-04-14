"""Dataset detector for training/eval datasets."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import DatasetInfo, Finding, FindingType


@dataclass
class DatasetPattern:
    """Pattern for detecting datasets."""

    pattern: re.Pattern[str]
    source: str


class DatasetDetector:
    """Detect dataset usage in code."""

    PATTERNS = [
        # HuggingFace datasets
        DatasetPattern(
            re.compile(r"from\s+datasets\s+import|load_dataset|datasets\.Dataset"),
            "huggingface",
        ),
        # PyTorch
        DatasetPattern(
            re.compile(r"torch\.utils\.data\.Dataset|DataLoader|class\s+\w+\(Dataset\)"),
            "pytorch",
        ),
        # TensorFlow
        DatasetPattern(
            re.compile(r"tensorflow_datasets|tfds\.load|tf\.data\.Dataset"),
            "tensorflow",
        ),
    ]

    @property
    def extensions(self) -> frozenset[str]:
        """File extensions this detector handles."""
        return frozenset({".py"})

    def detect(
        self, content: str, path: Path | str, matcher: Any | None = None
    ) -> Iterator[Finding]:
        """Detect dataset usage in code.

        Args:
            content: Source code content.
            path: Path to source file.
            matcher: Optional KB Matcher (unused for now).

        Yields:
            Finding for each dataset detected.
        """
        path_str = str(path)
        seen_sources: set[str] = set()

        for match in re.finditer(r"^.*$", content, re.MULTILINE):
            line = match.group()
            line_num = content[: match.start()].count("\n") + 1

            for pattern in self.PATTERNS:
                if pattern.pattern.search(line):
                    if pattern.source not in seen_sources:
                        seen_sources.add(pattern.source)
                        yield Finding(
                            type=FindingType.DATASET,
                            file_path=path_str,
                            confidence=0.9,
                            line=line_num,
                            dataset_info=DatasetInfo(source=pattern.source),
                        )
                    break
