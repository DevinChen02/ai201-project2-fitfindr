"""
Tests for the three FitFindr tools in tools.py.

Each tool is tested in isolation with hardcoded inputs, including at least one
test per documented failure mode:

    - search_listings  → no matches returns [] (never raises)
    - suggest_outfit   → empty wardrobe returns a non-empty string (never crashes)
    - create_fit_card  → empty/whitespace outfit returns an error string (never raises)

The LLM-backed happy-path tests only run when GROQ_API_KEY is available; the
failure-mode tests pass with or without a key because the guards and fallbacks
never depend on a live API call.

Run from the project root with:  pytest tests/
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


_HAS_KEY = bool(os.environ.get("GROQ_API_KEY"))


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, NOT an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_substring():
    # "M" is a case-insensitive substring match, so it matches "S/M", "M/L", etc.
    results = search_listings("graphic tee", size="m", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_ranks_best_match_first():
    # The bootleg graphic tee (lst_006) is the strongest "vintage graphic tee" hit.
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results[0]["id"] == "lst_006"


# ── suggest_outfit (failure mode: empty wardrobe) ─────────────────────────────

def test_suggest_outfit_empty_wardrobe_returns_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    # Empty wardrobe is graceful general advice, never empty, never a crash.
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_handles_missing_items_key():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, {})  # malformed wardrobe (no "items")
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card (failure mode: empty/whitespace outfit) ───────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    # Descriptive error string, not an exception.
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "couldn't" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("   \n  \t ", item)
    assert isinstance(result, str)
    assert "couldn't" in result.lower() or "no outfit" in result.lower()


# ── LLM happy-path tests (require a live GROQ_API_KEY) ─────────────────────────

@pytest.mark.skipif(not _HAS_KEY, reason="GROQ_API_KEY not set")
def test_suggest_outfit_with_wardrobe_returns_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


@pytest.mark.skipif(not _HAS_KEY, reason="GROQ_API_KEY not set")
def test_create_fit_card_outputs_vary_with_temperature():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = "Pair it with baggy straight-leg jeans and chunky white sneakers."
    captions = {create_fit_card(outfit, item) for _ in range(3)}
    # Higher temperature should produce at least some variation across runs.
    assert len(captions) > 1
