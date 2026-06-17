# FitFindr

A Gradio app that searches secondhand clothing listings, suggests outfits from your wardrobe, and generates a shareable fit card — all from a single natural language query.

## Video Demo
<div>
    <a href="https://www.loom.com/share/d4495b10c35445deb465c42013f93149">
      <p>AI201 Project 2 - FitFinder - Watch Video</p>
    </a>
    <a href="https://www.loom.com/share/d4495b10c35445deb465c42013f93149">
      <img width="300" src="https://cdn.loom.com/sessions/thumbnails/d4495b10c35445deb465c42013f93149-6a22a3ccc5f62ff9-full-play.gif#t=0.1">
    </a>
</div>

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Run tests:
```bash
pytest tests/
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the 40-item mock listings dataset (`data/listings.json`) for items matching the user's query. Entirely deterministic — no LLM involved. Rankings are reproducible across runs.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `description` | `str` | yes | Free-text keywords describing the item (e.g. `"vintage graphic tee"`). Tokenized and scored against each listing's `title`, `style_tags`, `category`, and `description` with field weights (title=3, style_tags=2, category=2, description=1). |
| `size` | `str \| None` | no | Size filter (e.g. `"M"`). Case-insensitive substring match, so `"M"` matches `"S/M"` and `"M/L"`. `None` skips size filtering. |
| `max_price` | `float \| None` | no | Inclusive price ceiling in dollars. Listings with `price > max_price` are excluded. `None` skips price filtering. |

**Output:** `list[dict]` — matching listing records sorted by relevance score, highest first. Empty list `[]` if nothing matches (never raises). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str).

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Asks the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfits that style the thrifted find using pieces from the user's wardrobe. Handles empty wardrobes by offering general styling guidance instead.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `new_item` | `dict` | yes | A listing dict (the item the user is considering). The prompt is built from its `title`, `category`, `colors`, `style_tags`, and `description`. |
| `wardrobe` | `dict` | yes | A wardrobe dict shaped `{"items": [...]}`. The `items` list may be empty — that is not an error. |

**Output:** `str` — a non-empty natural-language outfit suggestion. When the wardrobe has items, the suggestion names specific wardrobe pieces by name. When the wardrobe is empty, it gives general styling advice (category pairings, color guidance, vibe). Falls back to a deterministic rule-based string if the LLM call fails. Never returns an empty string.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Turns the outfit suggestion and item details into a 2–4 sentence casual social media caption (OOTD style). Runs at temperature 0.9 so captions vary across calls for the same input.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `outfit` | `str` | yes | The outfit suggestion string from `suggest_outfit()`. If empty or whitespace, returns a descriptive error string instead of calling the LLM. |
| `new_item` | `dict` | yes | The selected listing dict — used for `title`, `price`, and `platform` in the caption. |

**Output:** `str` — a 2–4 sentence casual caption that mentions the item name, price, and platform exactly once each. If `outfit` is empty/whitespace, returns a plain error message instead (e.g. `"Couldn't generate a fit card — no outfit suggestion was provided."`). Falls back to a template caption if the LLM call fails. Never raises.

---

## Planning Loop

`run_agent(query, wardrobe)` in [agent.py](agent.py) runs a **fixed linear pipeline** with one early-exit branch:

```
User query
    │
    ▼
_new_session()          — initialize session dict
    │
    ▼
parse_query()           — regex-extract description, size, max_price
    │
    ▼
search_listings()       — keyword search + filter
    │
    ├─ results == []  →  session["error"] = "No listings matched…"
    │                    return session  (EARLY EXIT — no LLM called)
    │
    └─ results non-empty
            │
            ▼
        selected_item = results[0]
            │
            ▼
        suggest_outfit()   — LLM outfit suggestion
            │
            ▼
        create_fit_card()  — LLM fit card caption
            │
            ▼
        return session
```

**Query parsing** (`parse_query`) uses regex to extract `max_price` ("under $30", "below 30", "< 30") and `size` ("size M", "in M", or standalone size token like "XS"/"XXL"/"W30") from the raw query. The remaining text after stripping those phrases becomes the `description` keyword string. If stripping would leave `description` empty, it falls back to the raw query.

**Tool sequencing** is determined purely by position in the pipeline — there is no open-ended "pick a tool" loop. The only decision point is the empty-results branch after `search_listings`. If results exist, all three tools always run in order.

---

## State Management

All state lives in a single **session dict** created by `_new_session(query, wardrobe)`. Each step writes its output into a named field; subsequent steps read from that field, not from local variables. This makes the full run inspectable from `app.py` or the CLI by reading `session` directly.

| Field | Type | Written by | Read by |
|-------|------|------------|---------|
| `query` | `str` | `_new_session` | `parse_query` |
| `wardrobe` | `dict` | `_new_session` | `suggest_outfit` |
| `parsed` | `dict` (`description`, `size`, `max_price`) | `parse_query` | `search_listings` call |
| `search_results` | `list[dict]` | `search_listings` | empty-check + `selected_item` assignment |
| `selected_item` | `dict \| None` | Step 4 (`= search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | `str \| None` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `str \| None` | `create_fit_card` | `app.py` panel 3 |
| `error` | `str \| None` | empty-results branch | **checked first** by `app.py` / CLI |

On the error path, only `error` is populated; `outfit_suggestion` and `fit_card` remain `None`. Consumers (`app.py`, CLI) always check `session["error"]` before reading output fields.

---

## Error Handling

### `search_listings` — no results

**Failure mode:** the query, size, and price combination matches zero listings.

**Agent response:** `search_listings` returns `[]` (never raises). The planning loop detects the empty list, constructs a specific error message that echoes the parsed filters back to the user with concrete suggestions, sets `session["error"]`, and returns the session immediately — `suggest_outfit` and `create_fit_card` are never called.

**Concrete example from testing:** querying `"designer ballgown"` with `size="XXS"` and `max_price=5` returns `[]`. The test `test_search_empty_results` in [tests/test_tools.py](tests/test_tools.py) asserts `results == []`. In the full agent, `run_agent("designer ballgown size XXS under $5", wardrobe)` sets `session["error"]` to `"No secondhand listings matched 'designer ballgown' under $5 in size XXS. Try removing the size filter, raising your price ceiling, or using broader keywords."` The Gradio UI shows this message in panel 1 and leaves the outfit and fit-card panels empty (visible in `Failure Mode.png`).

---

### `suggest_outfit` — empty wardrobe

**Failure mode:** the user selects "Empty wardrobe (new user)" — `wardrobe["items"]` is `[]`.

**Agent response:** not treated as an error. The tool detects the empty list and switches to a general styling prompt (asking the LLM what categories, colors, and silhouettes pair well with the item) rather than trying to reference named wardrobe pieces. The pipeline continues to `create_fit_card` normally. If the Groq call itself fails, a `try/except` returns a deterministic rule-based fallback built from the item's `colors` and `category` so the run still completes.

**Concrete example from testing:** `test_suggest_outfit_empty_wardrobe_returns_string` calls `suggest_outfit(item, get_empty_wardrobe())` and asserts the result is a non-empty string. Additionally, `test_suggest_outfit_handles_missing_items_key` passes a completely malformed `{}` wardrobe (no `"items"` key) and still gets a non-empty string back — the tool handles the missing key via `(wardrobe or {}).get("items", [])`.

---

### `create_fit_card` — empty outfit string

**Failure mode:** `outfit` is an empty or whitespace-only string.

**Agent response:** the tool guards at the top of the function before any LLM call. If `outfit.strip()` is falsy, it returns a descriptive error string that names the item, its price, and its platform — e.g. `"Couldn't generate a fit card — no outfit suggestion was provided. Here's the listing on its own: Graphic Tee — 2003 Tour Bootleg Style, $24 on depop."` — never raises. If the LLM call fails for any other reason, a `try/except` returns a simple template caption so the user always receives something.

**Concrete example from testing:** `test_create_fit_card_empty_outfit_returns_error_string` calls `create_fit_card("", item)` and asserts the result is a non-empty string containing `"couldn't"`. `test_create_fit_card_whitespace_outfit_returns_error_string` passes `"   \n  \t "` and confirms the same guard fires.

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30"`

**Step 1 — `parse_query`:**
- Input: `"vintage graphic tee under $30"`
- Why: extracts structured params from raw text so `search_listings` gets typed arguments.
- Output: `{"description": "vintage graphic tee", "size": None, "max_price": 30.0}`

**Step 2 — `search_listings`:**
- Tool: `search_listings("vintage graphic tee", size=None, max_price=30.0)`
- Why this tool: retrieves ranked candidates from the dataset before involving any LLM.
- Output: list of matching listings. `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style", $24, depop) ranks first — `"graphic"`, `"tee"`, and `"vintage"` all hit its title and style_tags, giving it the highest weighted score. `selected_item` is set to `lst_006`.

**Step 3 — `suggest_outfit`:**
- Tool: `suggest_outfit(lst_006, example_wardrobe)`
- Why this tool: translates a raw listing into wearable looks anchored to the user's actual closet.
- Output: `"Pair the Graphic Tee — 2003 Tour Bootleg Style with your Baggy straight-leg jeans, dark wash and Chunky white sneakers for a laid-back streetwear look. For a cooler-weather outfit, layer your Vintage black denim jacket on top and swap the sneakers for your Black combat boots."`

**Step 4 — `create_fit_card`:**
- Tool: `create_fit_card(outfit_suggestion, lst_006)`
- Why this tool: packages the outfit into a shareable caption for the final output panel.
- Output: `"Snagged this Graphic Tee — 2003 Tour Bootleg Style for $24 on depop and honestly couldn't be happier 🖤 Styling it with my baggy dark-wash jeans and chunky sneakers for that effortless vintage-streetwear vibe — thrifted fits just hit different."`

**Final output to user:** Panel 1 shows the formatted listing (title, price, size, condition, platform). Panel 2 shows the outfit suggestion. Panel 3 shows the fit card caption.

---

## Spec Reflection

**One way `planning.md` helped during implementation:**

Writing out the State Management table before any code forced an explicit decision about which session field each tool reads from and writes to. When implementing `run_agent`, that table served as a direct checklist: if `suggest_outfit` needed the selected listing, it had to come from `session["selected_item"]`, not a local variable. This prevented the common mistake of passing raw local results between steps, which would have made the session dict incomplete and broken the `app.py` read path.

**One divergence from the spec, and why:**

The planning doc described `parse_query` as an "internal parsing step inside the planning loop rather than a standalone agent tool," but in the final implementation it became its own named function (`parse_query`) in [agent.py](agent.py) with its own regex constants and docstring. The divergence was intentional: extracting it made the logic independently testable and kept `run_agent` readable. The spec's intent (it is not an agent-facing tool) is preserved — `parse_query` is never in the tool list and is never called by anything outside `run_agent`.

---

## AI Usage

### Instance 1 — `suggest_outfit` and `create_fit_card` implementations (Claude)

**Input to AI:** The Tool 2 and Tool 3 blocks from `planning.md` (what each function does, its parameters and types, the empty-wardrobe branch logic, the `_get_groq_client()` helper signature, and the fallback requirements), plus the `wardrobe_schema.json` item structure and one example listing dict.

**What it produced:** Claude generated both functions in one pass, correctly branching on `wardrobe["items"] == []`, formatting the wardrobe into a prompt block, and wrapping both Groq calls in `try/except`. It also produced the `_format_item`, `_rule_based_outfit`, and `_fallback_caption` helpers without being asked, mirroring the naming convention from the existing stub.

**What I changed:** The initial `suggest_outfit` prompt sent to the LLM was generic ("style this item"). I rewrote the `user_prompt` strings to be more directive — specifying "reference specific wardrobe pieces by name" for the non-empty branch and "what kinds of pieces, colors, and silhouettes pair well" for the empty branch. I also set `temperature=0.7` for `suggest_outfit` (Claude left it at the default) and `temperature=0.9` for `create_fit_card` as specified in the planning doc.

---

### Instance 2 — `run_agent` and `parse_query` implementation (Claude)

**Input to AI:** The Planning Loop section and State Management table from `planning.md` (the 7-step numbered sequence, the ASCII architecture diagram, and the Mermaid flowchart), plus the `_new_session()` docstring and `run_agent()` docstring from [agent.py](agent.py).

**What it produced:** Claude implemented both functions matching the spec almost exactly — `parse_query` with the two compiled regex patterns (`_PRICE_RE`, `_SIZE_RE`), span-removal logic for cleaning the description, and the fallback to the raw query if `description` would be empty. `run_agent` followed the 7-step sequence with the early return on empty results.

**What I changed:** The generated `_SIZE_RE` only matched `"size M"` with a leading keyword but missed standalone size tokens like a bare `"M"` or `"XL"` in the middle of a query. I extended the pattern to add a second alternation for the short unambiguous size codes (`XXS|XS|XL|XXL|XXL|W\d{2}`), since those tokens are unambiguous enough to match without a "size" prefix — single-letter tokens like bare `"M"` were intentionally excluded to avoid false positives (e.g. "M" in a brand name). I also added `.strip(" ,.-")` on the description cleanup, which the generated code omitted, to handle trailing punctuation left over after stripping price phrases like `"under $30,"`.
