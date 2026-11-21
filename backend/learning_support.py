"""Small, transparent heuristics for adjusting tutor scaffolding."""
import re
from datetime import datetime, timedelta, timezone

STRUGGLE = re.compile(r"\b(i\s*(?:don't|do not|can't|cannot)\s*understand|confused|stuck|lost|still not|doesn't work|error|wrong|why is this failing)\b", re.I)
PROGRESS = re.compile(r"\b(i understand|got it|that makes sense|solved it|works now|thank you)\b", re.I)


def _words(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9_]+", value.lower()) if len(word) > 2}


def estimate_support_level(message: str, recent_messages: list, previous_score: int = 1) -> tuple[int, int]:
    """Return support level 1..5 and repeated-loop count; this is not diagnosis."""
    if PROGRESS.search(message):
        return max(1, previous_score - 2), 0

    user_messages = [item for item in recent_messages if item.get("role") == "user"][-5:]
    loops = 0
    current_words = _words(message)
    for item in reversed(user_messages):
        prior_words = _words(str(item.get("content", "")))
        union = current_words | prior_words
        similarity = len(current_words & prior_words) / max(1, len(union))
        if similarity >= 0.55:
            loops += 1
        else:
            break

    score = min(5, max(1, previous_score))
    if STRUGGLE.search(message):
        score += 2
    elif any(word in message.lower() for word in ("traceback", "exception", "undefined", "segmentation fault")):
        score += 1
    if loops:
        score += min(2, loops)
    return min(5, score), loops
