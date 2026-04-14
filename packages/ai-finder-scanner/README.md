# ai-finder-scanner

Scanner library for AI Finder.

## Installation

```bash
pip install ai-finder-scanner
```

## Usage

```python
from ai_finder_scanner import Scanner

scanner = Scanner()
result = scanner.scan("/path/to/project")

for finding in result.findings:
    print(finding)
```

## License

MIT
