# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AI Finder standalone binary."""

import sys
from pathlib import Path

block_cipher = None

# Get the project root
project_root = Path(SPECPATH)

# Collect all package data
datas = [
    # Include KB schema SQL
    (str(project_root / "packages/ai-finder-kb/src/ai_finder_kb/schema.sql"), "ai_finder_kb"),
    # Include KB seed database if it exists
    (str(project_root / "packages/ai-finder-kb/src/ai_finder_kb/data"), "ai_finder_kb/data"),
]

# Filter out non-existent paths
datas = [(src, dst) for src, dst in datas if Path(src).exists()]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # KB package
    "ai_finder_kb",
    "ai_finder_kb.database",
    "ai_finder_kb.matcher",
    "ai_finder_kb.models",
    # Scanner package
    "ai_finder_scanner",
    "ai_finder_scanner.scanner",
    "ai_finder_scanner.discovery",
    "ai_finder_scanner.cache",
    "ai_finder_scanner.license",
    "ai_finder_scanner.models",
    # Detectors
    "ai_finder_scanner.detectors",
    "ai_finder_scanner.detectors.base",
    "ai_finder_scanner.detectors.python",
    "ai_finder_scanner.detectors.javascript",
    "ai_finder_scanner.detectors.go",
    "ai_finder_scanner.detectors.rust",
    "ai_finder_scanner.detectors.java",
    "ai_finder_scanner.detectors.ruby",
    # Parsers
    "ai_finder_scanner.parsers",
    "ai_finder_scanner.parsers.base",
    "ai_finder_scanner.parsers.gguf",
    "ai_finder_scanner.parsers.safetensors",
    "ai_finder_scanner.parsers.onnx",
    "ai_finder_scanner.parsers.pytorch",
    # Manifests
    "ai_finder_scanner.manifests",
    "ai_finder_scanner.manifests.base",
    "ai_finder_scanner.manifests.python",
    "ai_finder_scanner.manifests.npm",
    # Output formatters
    "ai_finder_scanner.output",
    "ai_finder_scanner.output.base",
    "ai_finder_scanner.output.json_output",
    "ai_finder_scanner.output.cyclonedx",
    "ai_finder_scanner.output.spdx",
    # CLI
    "ai_finder_cli",
    "ai_finder_cli.main",
    "ai_finder_cli.commands",
    "ai_finder_cli.commands.identify",
    "ai_finder_cli.commands.kb",
    # Standard library and dependencies
    "click",
    "click.core",
    "click.decorators",
    "click.exceptions",
    "click.formatting",
    "click.parser",
    "click.termui",
    "click.testing",
    "click.types",
    "click.utils",
    "sqlite3",
    "importlib.resources",
]

# Try to include osslili if available (with data files)
osslili_datas = []  # Define before try block
try:
    import osslili
    import os
    osslili_path = os.path.dirname(osslili.__file__)
    hiddenimports.extend([
        "osslili",
        "osslili.core",
        "osslili.core.models",
        "osslili.core.generator",
        "osslili.data",
        "osslili.data.spdx_licenses",
        "osslili.detectors",
        "osslili.detectors.license_detector",
        "osslili.utils",
        "osslili.extractors",
        "osslili.formatters",
    ])
    # Include osslili data files
    osslili_datas.append((os.path.join(osslili_path, "data"), "osslili/data"))
except ImportError:
    pass

# Try to include tree-sitter for relationship analysis (Python 3.10+)
tree_sitter_binaries = []
tree_sitter_datas = []
try:
    from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

    # Collect binaries and data for tree-sitter packages
    tree_sitter_packages = [
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_javascript",
        "tree_sitter_typescript",
        "tree_sitter_go",
        "tree_sitter_rust",
        "tree_sitter_java",
        "tree_sitter_ruby",
        "tree_sitter_php",
        "tree_sitter_c_sharp",
        "tree_sitter_cpp",
    ]

    for pkg in tree_sitter_packages:
        try:
            tree_sitter_binaries.extend(collect_dynamic_libs(pkg))
            tree_sitter_datas.extend(collect_data_files(pkg))
            hiddenimports.append(pkg)
        except Exception:
            pass  # Package not installed

except ImportError:
    pass

# Add osslili data files if available
datas.extend(osslili_datas)

# Add tree-sitter binaries and data
datas.extend(tree_sitter_datas)

a = Analysis(
    [str(project_root / "packages/ai-finder/src/ai_finder_cli/main.py")],
    pathex=[
        str(project_root / "packages/ai-finder/src"),
        str(project_root / "packages/ai-finder-scanner/src"),
        str(project_root / "packages/ai-finder-kb/src"),
    ],
    binaries=tree_sitter_binaries,
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
    name="ai-finder",
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
