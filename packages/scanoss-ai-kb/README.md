# scanoss-ai-kb

Knowledge Base library for SCANOSS AI.

## Installation

```bash
pip install scanoss-ai-kb
```

## Usage

```python
from scanoss_ai_kb import KnowledgeBase, Matcher

kb = KnowledgeBase()
matcher = kb.matcher

# Match SDK
result = matcher.match_sdk("openai")
```

## License

MIT
