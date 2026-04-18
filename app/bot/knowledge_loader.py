from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parent.parent.parent / "knowledge"


@lru_cache(maxsize=1)
def load_knowledge() -> str:
    """Concatenate all knowledge files into a single string for the system prompt.
    Cached on import; restart uvicorn to refresh.
    """
    parts: list[str] = []
    files = [
        "product/pricing.md",
        "product/modules.md",
        "product/objection_handling.md",
        "product/icp.md",
        "scoring/rules.md",
    ]
    for rel in files:
        p = KNOWLEDGE_ROOT / rel
        if p.exists():
            parts.append(f"\n\n===== {rel} =====\n{p.read_text(encoding='utf-8')}")
    return "".join(parts)
