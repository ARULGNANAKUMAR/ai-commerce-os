"""
commerce/language_service.py
──────────────────────────────
Lightweight, dependency-free language detection + intent classification.

Language detection:
  - Tamil script (Unicode U+0B80–U+0BFF) → "ta"
  - Latin script with common Tamil transliteration words → "tanglish"
  - Otherwise → "en"

Intent classification is keyword/rule-based (no LLM call required, so
chat always works even without an AI provider connected). This keeps
the AI provider reserved for the free-text response generation step,
matching the mock-fallback pattern already used in workflow/node_handlers.py.
"""

import re

TAMIL_SCRIPT_RE = re.compile(r"[\u0B80-\u0BFF]")

TANGLISH_MARKERS = {
    "venum", "vendam", "vendaam", "irukka", "iruku", "illa", "epdi", "eppadi",
    "evlo", "evalo", "nalla", "seri", "vanga", "vaanga", "kudunga", "poidu",
    "sollunga", "romba", "konjam", "enna", "yenna", "pannunga", "panren",
    "venuma", "kaasu", "vilai",
}

# ── Intent keyword buckets (English + Tanglish share latin script) ────
INTENT_KEYWORDS = {
    "greeting":         ["hi", "hello", "hey", "vanakkam", "good morning", "good evening"],
    "compare":          ["compare", "vs", "versus", "difference between", "which is better"],
    "recommend":        ["recommend", "suggest", "best", "which one should", "nallavaru", "nalla product"],
    "add_to_cart":      ["add to cart", "buy this", "add this", "vaanga", "order this", "i want to buy", "put in cart"],
    "remove_from_cart": ["remove from cart", "delete from cart", "take out", "edukanum vendaam", "cancel item"],
    "update_cart":      ["change quantity", "update quantity", "update cart", "make it"],
    "view_cart":        ["show cart", "my cart", "view cart", "what's in my cart", "cart eduku"],
    "checkout":         ["checkout", "buy now", "place order", "confirm order", "pay now", "proceed to pay"],
    "search":           ["show me", "find", "search", "looking for", "i want", "i need", "venum", "kavala", "do you have"],
}

# Tamil-script keyword → intent (small curated set)
TAMIL_INTENT_KEYWORDS = {
    "greeting":  ["வணக்கம்", "ஹலோ"],
    "compare":   ["ஒப்பிடு", "வித்தியாசம்"],
    "recommend": ["பரிந்துரை", "நல்லது"],
    "add_to_cart": ["வாங்க", "கார்ட்டில் சேர்"],
    "checkout":  ["செக்அவுட்", "பணம் செலுத்து"],
    "search":    ["தேடு", "வேண்டும்", "காட்டு"],
}


def detect_language(text: str) -> str:
    if not text:
        return "en"
    if TAMIL_SCRIPT_RE.search(text):
        return "ta"
    lowered = text.lower()
    tokens = set(re.findall(r"[a-zA-Z']+", lowered))
    if tokens & TANGLISH_MARKERS:
        return "tanglish"
    return "en"


def detect_intent(text: str, language: str = None) -> str:
    if not text:
        return "unknown"
    language = language or detect_language(text)
    lowered = text.lower().strip()

    if language == "ta":
        for intent, words in TAMIL_INTENT_KEYWORDS.items():
            if any(w in text for w in words):
                return intent
        return "search"  # Tamil script default: assume a search/browse intent

    tokens = set(re.findall(r"[a-zA-Z']+", lowered))

    # Cart intents: token-based (robust to natural phrasing like
    # "add the first one to cart" which doesn't contain the literal
    # substring "add to cart").
    has_cart = "cart" in tokens or "basket" in tokens
    if has_cart:
        if tokens & {"remove", "delete", "take", "drop"}:
            return "remove_from_cart"
        if tokens & {"show", "view", "whats", "what's", "see", "check"}:
            return "view_cart"
        if tokens & {"update", "change", "make", "set"} and re.search(r"\d", lowered):
            return "update_cart"
        if tokens & {"add", "put", "buy", "get", "want", "order"}:
            return "add_to_cart"
        return "view_cart"

    if any(kw in lowered for kw in ["buy this", "order this", "i want to buy", "add this", "vaanga"]):
        return "add_to_cart"

    # Order matters: check more specific intents before generic "search"
    for intent in ["checkout", "compare", "recommend", "greeting"]:
        for kw in INTENT_KEYWORDS[intent]:
            if kw in lowered:
                return intent

    for kw in INTENT_KEYWORDS["search"]:
        if kw in lowered:
            return "search"

    # Fallback: if message looks like a short noun phrase, treat as search
    if len(lowered.split()) <= 6:
        return "search"
    return "unknown"


def extract_budget(text: str) -> float | None:
    """Extract a rupee amount from free text, e.g. 'under 2000', '₹1500', 'budget is 3k'.
    Requires a currency marker or a budget-context word near the number to avoid
    false positives on unrelated numbers (e.g. 'top 5 products')."""
    if not text:
        return None
    lowered = text.lower()
    m = re.search(
        r"(?:₹|rs\.?|inr|under|below|budget(?:\s+is|\s+of)?|within|max)\s*(\d+(?:\.\d+)?)\s*(k)?",
        lowered,
    )
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2) == "k":
        val *= 1000
    return val if val > 0 else None
