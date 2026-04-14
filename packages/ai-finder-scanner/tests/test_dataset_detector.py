"""Tests for dataset detector."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.detectors.datasets import DatasetDetector
from ai_finder_scanner.models import FindingType


class TestDatasetDetector:
    @pytest.fixture
    def detector(self) -> DatasetDetector:
        return DatasetDetector()

    def test_detect_huggingface_dataset(self, detector: DatasetDetector) -> None:
        code = """
from datasets import load_dataset
dataset = load_dataset("squad", split="train")
"""
        findings = list(detector.detect(code, Path("train.py")))

        assert len(findings) >= 1
        assert findings[0].type == FindingType.DATASET
        assert findings[0].dataset_info.source == "huggingface"

    def test_detect_torch_dataset(self, detector: DatasetDetector) -> None:
        code = """
from torch.utils.data import Dataset, DataLoader
class MyDataset(Dataset):
    pass
"""
        findings = list(detector.detect(code, Path("data.py")))

        assert len(findings) >= 1
        assert findings[0].dataset_info.source == "pytorch"

    def test_detect_tensorflow_dataset(self, detector: DatasetDetector) -> None:
        code = """
import tensorflow_datasets as tfds
dataset = tfds.load("mnist")
"""
        findings = list(detector.detect(code, Path("tf_data.py")))

        assert len(findings) >= 1
        assert findings[0].dataset_info.source == "tensorflow"

    def test_no_false_positives(self, detector: DatasetDetector) -> None:
        code = """
import requests
response = requests.get("https://api.example.com")
"""
        findings = list(detector.detect(code, Path("app.py")))

        assert len(findings) == 0
