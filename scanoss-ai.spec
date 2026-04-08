# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SCANOSS AI standalone binary."""

import sys
from pathlib import Path

block_cipher = None

# Get the project root
project_root = Path(SPECPATH)

# Collect all package data
datas = [
    # Include KB schema SQL
    (str(project_root / "packages/scanoss-ai-kb/src/scanoss_ai_kb/schema.sql"), "scanoss_ai_kb"),
    # Include KB seed database if it exists
    (str(project_root / "packages/scanoss-ai-kb/src/scanoss_ai_kb/data"), "scanoss_ai_kb/data"),
]

# Filter out non-existent paths
datas = [(src, dst) for src, dst in datas if Path(src).exists()]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # KB package
    "scanoss_ai_kb",
    "scanoss_ai_kb.database",
    "scanoss_ai_kb.matcher",
    "scanoss_ai_kb.models",
    # Scanner package
    "scanoss_ai_scanner",
    "scanoss_ai_scanner.scanner",
    "scanoss_ai_scanner.discovery",
    "scanoss_ai_scanner.cache",
    "scanoss_ai_scanner.license",
    "scanoss_ai_scanner.models",
    # Detectors
    "scanoss_ai_scanner.detectors",
    "scanoss_ai_scanner.detectors.base",
    "scanoss_ai_scanner.detectors.python",
    "scanoss_ai_scanner.detectors.javascript",
    "scanoss_ai_scanner.detectors.go",
    "scanoss_ai_scanner.detectors.rust",
    "scanoss_ai_scanner.detectors.java",
    "scanoss_ai_scanner.detectors.ruby",
    # Parsers
    "scanoss_ai_scanner.parsers",
    "scanoss_ai_scanner.parsers.base",
    "scanoss_ai_scanner.parsers.gguf",
    "scanoss_ai_scanner.parsers.safetensors",
    "scanoss_ai_scanner.parsers.onnx",
    "scanoss_ai_scanner.parsers.pytorch",
    # Manifests
    "scanoss_ai_scanner.manifests",
    "scanoss_ai_scanner.manifests.base",
    "scanoss_ai_scanner.manifests.python",
    "scanoss_ai_scanner.manifests.npm",
    # Output formatters
    "scanoss_ai_scanner.output",
    "scanoss_ai_scanner.output.base",
    "scanoss_ai_scanner.output.json_output",
    "scanoss_ai_scanner.output.cyclonedx",
    "scanoss_ai_scanner.output.spdx",
    # CLI
    "scanoss_ai_cli",
    "scanoss_ai_cli.main",
    "scanoss_ai_cli.commands",
    "scanoss_ai_cli.commands.identify",
    "scanoss_ai_cli.commands.kb",
    # Standard library
    "click",
    "sqlite3",
    "importlib.resources",
]

# Try to include osslili if available
try:
    import osslili
    hiddenimports.append("osslili")
except ImportError:
    pass

a = Analysis(
    [str(project_root / "packages/scanoss-ai/src/scanoss_ai_cli/main.py")],
    pathex=[
        str(project_root / "packages/scanoss-ai/src"),
        str(project_root / "packages/scanoss-ai-scanner/src"),
        str(project_root / "packages/scanoss-ai-kb/src"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "torch",
        "tensorflow",
        "transformers",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="scanoss-ai",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
