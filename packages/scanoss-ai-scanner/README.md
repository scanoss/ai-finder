# scanoss-ai-scanner

Scanner library for SCANOSS AI.

## Installation

```bash
pip install scanoss-ai-scanner
```

## Usage

```python
from scanoss_ai_scanner import Scanner

scanner = Scanner()
result = scanner.scan("/path/to/project")

for finding in result.findings:
    print(finding)
```

## License

Apache-2.0
