"""Manifest parsers for various package managers."""

from __future__ import annotations

from .base import BaseManifestParser
from .cargo import CargoManifestParser
from .cocoapods import CocoaPodsManifestParser
from .composer import ComposerManifestParser
from .gemfile import GemfileManifestParser
from .gomod import GoModManifestParser
from .gradle import GradleManifestParser
from .maven import MavenManifestParser
from .npm import NpmManifestParser
from .nuget import NuGetManifestParser
from .python import PythonManifestParser
from .swiftpm import SwiftPMManifestParser

__all__ = [
    "BaseManifestParser",
    "CargoManifestParser",
    "CocoaPodsManifestParser",
    "ComposerManifestParser",
    "GemfileManifestParser",
    "GoModManifestParser",
    "GradleManifestParser",
    "MavenManifestParser",
    "NpmManifestParser",
    "NuGetManifestParser",
    "PythonManifestParser",
    "SwiftPMManifestParser",
]
