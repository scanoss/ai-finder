# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

[Provide a brief description of what this project does, its purpose, and key use cases]

**Key Features:**
- Feature 1: Description
- Feature 2: Description
- Feature 3: Description

## Architecture

### Core Components
- **Component 1**: Description and responsibility
- **Component 2**: Description and responsibility
- **Component 3**: Description and responsibility

### Key Modules
[Describe the main modules/packages and their purposes]

```
project_name/
├── core/           # Core functionality
├── utils/          # Utility functions
├── cli.py          # Command-line interface
└── __init__.py     # Package initialization
```

## Development Guidelines

### Core Principles
1. **Simplicity**: Keep code simple and readable
2. **Testing**: Write tests for new functionality
3. **Documentation**: Document public APIs
4. **Performance**: Consider performance implications

### Code Style
- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Write docstrings for public functions
- Keep functions focused and small

### Testing Strategy
- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete workflows

## Development Commands

### Setup
```bash
# Clone repository
git clone https://github.com/semclone/[project-name].git
cd [project-name]

# Install in development mode
pip install -e .[dev]

# Install pre-commit hooks (if using)
pre-commit install
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=project_name

# Run specific test file
pytest tests/test_specific.py -v
```

### Code Quality
```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy project_name/
```

### Building and Distribution
```bash
# Build package
python -m build

# Install locally
pip install -e .

# Publish to PyPI (after testing on TestPyPI)
python -m twine upload dist/*
```

## Integration with SEMCL.ONE

[Describe how this project integrates with other SEMCL.ONE ecosystem components]

- Works with **component1** for [purpose]
- Integrates with **component2** for [purpose]
- Complements **component3** for [purpose]

## Common Tasks

### Adding a New Feature
1. Create a feature branch: `git checkout -b feature/your-feature`
2. Implement the feature with tests
3. Update documentation
4. Submit a pull request

### Fixing a Bug
1. Create a bugfix branch: `git checkout -b bugfix/issue-number`
2. Write a failing test that reproduces the bug
3. Fix the bug
4. Ensure all tests pass
5. Submit a pull request

### Updating Dependencies
1. Update dependency versions in `pyproject.toml`
2. Run tests to ensure compatibility
3. Update CHANGELOG.md
4. Submit a pull request

## Troubleshooting

### Common Issues

**Issue 1**: [Description]
- **Solution**: [How to fix]

**Issue 2**: [Description]
- **Solution**: [How to fix]

## Project Structure

```
project-name/
├── project_name/       # Main package
│   ├── __init__.py    # Package initialization
│   ├── core/          # Core functionality
│   ├── utils/         # Utilities
│   └── cli.py         # CLI interface
├── tests/             # Test suite
├── docs/              # Documentation
├── scripts/           # Utility scripts
├── README.md          # Project README
├── CONTRIBUTING.md    # Contribution guidelines
├── LICENSE            # Apache 2.0 license
├── pyproject.toml     # Package configuration
└── CHANGELOG.md       # Version history
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

---

Copyright (c) 2025-2026 SEMCL.ONE. All Rights Reserved.

_Part of the [SEMCL.ONE](https://semcl.one) ecosystem for comprehensive OSS compliance and code analysis._
