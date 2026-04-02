from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

@dataclass
class RewriteResult:
    text_en: str
    tag: Optional[str]

def rewrite_if_needed(
    *,
    is_crisis: bool,
    user_raw: str,
    user_en: str,
    base_reply_en: str,
    sentiment: Dict[str, Any],
    source: str,
    rewrite_reply_en_func,
) -> RewriteResult:

    if is_crisis:
        return RewriteResult(text_en=base_reply_en, tag="skip_crisis")

    rewritten, tag = rewrite_reply_en_func(
        user_raw=user_raw,
        user_en=user_en,
        base_reply_en=base_reply_en,
        sentiment=sentiment or {},
        source=source,
    )
    return RewriteResult(text_en=rewritten, tag=tag)