import re
from typing import Optional


_CODE_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_SELECT_RE = re.compile(r"\bSELECT\b[\s\S]*?;?\s*$", re.IGNORECASE)


def extract_sql(text: str) -> Optional[str]:
    """Extract a SQL snippet from a model response.

    Strategy:
    - Prefer fenced code blocks (```sql ... ``` or ``` ... ```)
    - Fallback to finding the first SELECT statement in the text
    - Return None if nothing looks like a SELECT query
    """
    if not text:
        return None

    # 1) fenced code block
    m = _CODE_BLOCK_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        # strip surrounding backticks/newlines
        candidate = candidate.strip(' \n;')
        if _SELECT_RE.search(candidate):
            return candidate

    # 2) first SELECT ... (greedy until end or semicolon)
    m2 = _SELECT_RE.search(text)
    if m2:
        return m2.group(0).strip().rstrip(';')

    return None
