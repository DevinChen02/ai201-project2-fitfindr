"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Groq model used by the two LLM-backed tools.
_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────
# Field weights for keyword scoring — a hit in the title counts more than one in
# the free-text description. Keeps ranking deterministic (no LLM involved).
_FIELD_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("title", 3),
    ("style_tags", 2),
    ("category", 2),
    ("description", 1),
)

# Common words stripped from queries so they don't inflate keyword scores.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "on", "of", "to",
    "is", "it", "this", "that", "i", "im", "looking", "want", "need", "some",
}


def _tokenize(text: str) -> list[str]:
    """Lowercase and split text into alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _score_listing(query_tokens: list[str], listing: dict) -> int:
    """Score a listing by weighted keyword overlap across its text fields."""
    score = 0
    for field, weight in _FIELD_WEIGHTS:
        value = listing.get(field, "")
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        field_tokens = set(_tokenize(str(value)))
        for token in query_tokens:
            if token in field_tokens:
                score += weight
    return score


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = [t for t in _tokenize(description) if t not in _STOPWORDS]

    scored: list[tuple[int, dict]] = []
    for listing in listings:
        # 1. Price ceiling (inclusive).
        price = listing.get("price")
        if max_price is not None and price is not None and price > max_price:
            continue

        # 2. Size filter — case-insensitive substring ("M" matches "S/M").
        if size is not None and size.strip():
            if size.strip().lower() not in str(listing.get("size", "")).lower():
                continue

        # 3. Keyword relevance — drop anything that matches nothing.
        score = _score_listing(query_tokens, listing) if query_tokens else 0
        if score > 0:
            scored.append((score, listing))

    # 4. Highest score first; stable sort keeps dataset order on ties.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────
def _format_item(item: dict) -> str:
    """Render the key fields of a listing into a compact prompt block."""
    return "\n".join(
        [
            f"Title: {item.get('title', '')}",
            f"Category: {item.get('category', '')}",
            f"Colors: {', '.join(item.get('colors', []))}",
            f"Style tags: {', '.join(item.get('style_tags', []))}",
            f"Description: {item.get('description', '')}",
        ]
    )


def _rule_based_outfit(new_item: dict) -> str:
    """Deterministic styling fallback used when the LLM call fails."""
    colors = ", ".join(new_item.get("colors", [])) or "neutral"
    title = new_item.get("title", "this piece")
    category = new_item.get("category", "item")
    return (
        f"Style this {colors} {title} as the statement piece: pair it with "
        f"simple neutral basics that let the {category} stand out, add a "
        f"complementary layer, and finish with chunky sneakers or boots."
    )


def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    items = (wardrobe or {}).get("items", [])
    item_block = _format_item(new_item)

    if not items:
        # Empty wardrobe is NOT an error: ask for general styling guidance.
        user_prompt = (
            "A shopper is considering this secondhand item but hasn't entered "
            "any wardrobe pieces yet. Give general styling guidance for the item "
            "on its own: what kinds of pieces, colors, and silhouettes pair well, "
            "and what vibe it suits. Keep it to 2-4 sentences, concrete and "
            "friendly.\n\n"
            f"ITEM:\n{item_block}"
        )
    else:
        wardrobe_block = "\n".join(
            f"- {w.get('name', 'piece')} "
            f"({w.get('category', '')}; {', '.join(w.get('colors', []))})"
            for w in items
        )
        user_prompt = (
            "Suggest 1-2 complete outfits that style the NEW ITEM using pieces "
            "from the shopper's WARDROBE below. Reference specific wardrobe "
            "pieces by name. Keep it concise (2-5 sentences total), practical, "
            "and friendly.\n\n"
            f"NEW ITEM:\n{item_block}\n\n"
            f"WARDROBE:\n{wardrobe_block}"
        )

    system_prompt = (
        "You are FitFindr, a thrift-fashion stylist who gives specific, wearable "
        "outfit advice in a warm, encouraging tone."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        # Network/auth/parse failure — fall back so the pipeline still completes.
        pass

    return _rule_based_outfit(new_item)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────
def _format_price(price) -> str:
    """Format a numeric price as a clean dollar string (24.0 -> '$24')."""
    if isinstance(price, (int, float)):
        return f"${price:g}"
    return "a great price"


def _fallback_caption(new_item: dict) -> str:
    """Simple template caption used when the LLM call fails."""
    title = new_item.get("title", "this find")
    platform = new_item.get("platform", "secondhand")
    return (
        f"Thrifted this {title} for {_format_price(new_item.get('price'))} on "
        f"{platform}. Secondhand and totally one of a kind. ✨"
    )


def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: an empty/whitespace outfit is a known failure mode — never raise.
    if not outfit or not outfit.strip():
        title = new_item.get("title", "this listing")
        platform = new_item.get("platform", "secondhand")
        return (
            "Couldn't generate a fit card — no outfit suggestion was provided. "
            f"Here's the listing on its own: {title}, "
            f"{_format_price(new_item.get('price'))} on {platform}."
        )

    title = new_item.get("title", "this find")
    platform = new_item.get("platform", "secondhand")
    price_str = _format_price(new_item.get("price"))

    system_prompt = (
        "You write short, authentic social-media outfit captions (OOTD posts). "
        "Casual and real — never a product description."
    )
    user_prompt = (
        "Write a 2-4 sentence caption for an Instagram/TikTok OOTD post about a "
        "thrifted find. Make it casual and authentic, capture the outfit vibe in "
        "specific terms, and mention the item name, price, and platform naturally "
        "exactly once each. One or two emojis max — no hashtag spam.\n\n"
        f"ITEM NAME: {title}\n"
        f"PRICE: {price_str}\n"
        f"PLATFORM: {platform}\n\n"
        f"OUTFIT:\n{outfit}"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9,  # higher temp → captions vary across runs
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass

    return _fallback_caption(new_item)
