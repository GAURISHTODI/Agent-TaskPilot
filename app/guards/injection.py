import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)

_PATTERNS = {
    "ignore_instructions": r"(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+|previous\s+|prior\s+|above\s+)*"
                           r"(?:rules|instructions?|prompts?|guidelines|polic(?:y|ies)|everything)",
    "role_override": r"you are now|act as (?:a |an )?(?:admin|root|system)|developer mode|jailbreak|pretend (?:to be|you)",
    "prompt_exfiltration": r"(?:reveal|show|print|repeat)\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instructions)",
    "fake_system_tag": r"</?\s*(?:system|assistant|instructions?)\s*>|\[/?inst\]|###\s*system",
    "action_hijack": r"(?:send|make|process|release)\s+(?:the\s+|a\s+)?(?:payment|money|transfer)|mark (?:it |this )?as paid"
                     r"|without (?:any )?(?:approval|human|review)|skip (?:the )?approval|auto[- ]?(?:book|approve)",
    "hinglish_override": r"pichle instructions|rules ignore|ignore karo|approval ke bina",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in _PATTERNS.items()}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return re.sub(r"\s+", " ", text)


def scan(text: str) -> list[str]:
    """Names of injection patterns found. Customer/vendor text is DATA; a hit raises risk, never trust."""
    t = normalise(text)
    return [name for name, rx in _COMPILED.items() if rx.search(t)]
