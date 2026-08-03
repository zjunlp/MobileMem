# `backends/llm/` — LLM Client

Text-LLM access used by every generator: model selection, chat requests, JSON
extraction / parsing, and per-call logging. The implementation lives in
`request.py`; import via this package (`from backends.llm import ...`).

Imported as:

```python
from backends.llm import get_text_llm_model, llm_request, set_log_context
```
