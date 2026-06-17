# FitFindr — planning.md


## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
This tool helps search the stuff the user is looking for from some websites, the stuffs meet the requirements of the user, size, name, color, prices, etc.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): keywords describing the item (e.g. "vintage graphic tee").
- `size` (str, optional): size to filter by; case-insensitive (e.g. "M" matches "S/M"). Omit to skip.
- `max_price` (float, optional): price ceiling in dollars (inclusive). Omit to skip.

**What it returns:**

A list of matching listing dicts, sorted best-match first. Each has: `id`, `title`,
`description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`,
`brand`, `platform`. Returns an empty list (never raises) when nothing matches.

**What happens if it fails or returns nothing:**

If nothing matches it returns `[]`. The agent then tells the user no listings were
found and to try a different search, and does not proceed to the other tools.


### Tool 2: suggest_outfit

**What it does:**
 
 Once returns a list of the products, it will give some suggestions about the outfit, if it fits and the reasons. It will suggest if it fits with the existing wardrobe, and how to wear it.

**Input parameters:**

- `new_item` new items 
- `wardrobe` existing wardrobe

**What it returns:**

how to wear this item with existing clothes in the wardrobe


**What happens if it fails or returns nothing:**

Error path: If search_listings returns nothing, FitFindr tells the user what to try differently and stops — it does not call suggest_outfit with empty input.

### Tool 3: create_fit_card

**What it does:**

It checks how well does the new item fits the wardrobe, it gives some feedback for each item 


**Input parameters:**
the new item, and existing wardrobe

**What it returns:**

the suggestions and how well it fits for existing wardrobe

**What happens if it fails or returns nothing:**

It tells the user the wardrobe is empty, it could match anything

### Additional Tools (if any)

It can compare the prices from different websites and different item options

## Planning Loop

User query
    │
    ▼
┌─ Planning loop (repeat up to MAX_STEPS) ─────────────────────────┐
│                                                                  │
│   messages + TOOL_SCHEMAS  ──►  LLM (Groq, tool_choice="auto")   │
│                                       │                          │
│              ┌────────────────────────┴───────────────┐         │
│              │ model returns tool_call(s)              │ model   │
│              ▼                                         │ returns │
│   _execute_tool(name, args, session)                   │ no tool │
│     • search_listings → session.search_results,        │ call    │
│                          selected_item = results[0]    │  │      │
│     • suggest_outfit   → session.outfit_suggestion     │  ▼      │
│     • create_fit_card  → session.fit_card              │ final   │
│              │                                         │ text    │
│   append tool result to messages, loop again ──────────┘         │
└──────────────────────────────────────────────────────────────────┘
            │
            ▼
   After the loop: if fit_card is None → set session["error"]
   (no results found, or the model stopped early)
            │
            ▼
        Return session

**How does your agent decide which tool to call next?**

The agent is **LLM-driven**. It does not hardcode the tool order. On every turn,
`run_agent()` sends the running conversation plus the three tool schemas
(`TOOL_SCHEMAS`) to the Groq model with `tool_choice="auto"`, and the *model*
chooses which tool to call next — or replies with plain text to signal it is done.

The loop in `run_agent()` works like this:
1. Call the LLM with the messages + tool schemas.
2. If the response contains tool call(s), run each through `_execute_tool()`,
   append the result as a `tool` message, and loop again.
3. If the response has no tool calls, the model is finished — its text is the
   final reply and the loop breaks.
4. A `MAX_STEPS` cap bounds the loop so it can't run forever.

The system prompt steers the model toward the sensible order
(`search_listings` → `suggest_outfit` → `create_fit_card`) and tells it **not** to
style or caption when a search returns no results — but the decision each turn is
the model's, made from the tool results it has seen so far.

The model supplies only the *simple* arguments (search keywords, size, price, which
listing id to style). The heavy objects — the user's wardrobe and the full listing
dict — are injected from `session` by `_execute_tool()`, so the model never has to
round-trip them.


## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

There are two layers of state, and they stay in sync:

- **The `messages` list** is the LLM's working memory. The assistant's tool calls
  and each tool's result are appended to it, so on the next turn the model sees
  everything that has happened and can decide what to do next.
- **The `session` dict** (created once per run by `_new_session()`) is the
  structured source of truth the rest of the app reads from. `_execute_tool()`
  writes each tool's output into the right field as it runs.

When the model calls a tool, `_execute_tool()` does the bridging: it reads the
simple args the model supplied (plus any heavy objects it needs from `session`,
like `wardrobe`), runs the tool, writes the result into `session`, and returns a
short string that gets appended to `messages` for the model to read.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | `_new_session` | seeds the first user message |
| `messages` | the loop + `_execute_tool` | the LLM, every turn |
| `parsed` (`description`, `size`, `max_price`) | `_execute_tool` (from the model's search args) | logging / inspection |
| `search_results` | `_execute_tool` (`search_listings`) | `suggest_outfit`, error check |
| `selected_item` | `_execute_tool` (top result, or the `item_id` the model picked) | `suggest_outfit`, `create_fit_card`, `app.py` |
| `wardrobe` | `_new_session` | `_execute_tool` → `suggest_outfit` |
| `outfit_suggestion` | `_execute_tool` (`suggest_outfit`) | `create_fit_card`, `app.py` |
| `fit_card` | `_execute_tool` (`create_fit_card`) | `app.py` |
| `tool_calls` | the loop | inspection / debugging |
| `error` | the loop (after it ends, if no fit card was produced) | `app.py` (checked first) |

The tool functions in `tools.py` stay pure — they take plain arguments and return
plain values. Nothing is passed via globals; the `session` dict and the `messages`
list are the only carriers of state. `app.py` inspects the returned session,
checking `session["error"]` before reading the output fields.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns an empty list; `_execute_tool` reports `count: 0` to the model. The system prompt tells the model not to call the other tools, so it replies with a "try something different" message. After the loop, since no `fit_card` was produced, `run_agent` sets `session["error"]` (the model's message, or a default), and `app.py` shows it in the first panel. |
| suggest_outfit | Wardrobe is empty | Handled inside the tool: instead of failing, it switches to a prompt for general styling advice for the item, so it always returns a non-empty suggestion. |
| suggest_outfit | Called before any search results exist | `_execute_tool` returns an error string ("call search_listings first") instead of crashing, and the model can correct course. |
| create_fit_card | Outfit input is missing or incomplete | The tool guards against an empty/whitespace outfit and returns a descriptive error string rather than raising. `_execute_tool` also refuses to run it if `selected_item` or `outfit_suggestion` is missing. |
| (any) | Groq API / network failure | The whole loop is wrapped in `try/except`; on any exception `run_agent` sets `session["error"]` with the failure and returns, so `app.py` shows a clean message instead of a traceback. |
| (loop) | Model never finishes / loops | `MAX_STEPS` caps the iterations; if it ends without a fit card, `session["error"]` is set. |

---

## Architecture

```
                ┌──────────────────────────┐
   user query   │   app.py (Gradio UI)     │   reads session["error"],
  ────────────► │   handle_query()         │ ◄──── selected_item,
                └────────────┬─────────────┘       outfit_suggestion, fit_card
                             │ run_agent(query, wardrobe)
                             ▼
                ┌──────────────────────────┐        ┌──────────────────┐
                │  agent.py                │  reads/ │  session dict    │
                │  run_agent() loop        │ ◄─────► │  + messages list │
                │                          │  writes │  (state)         │
                │  ┌────────────────────┐  │        └──────────────────┘
                │  │ Groq LLM           │  │
                │  │ chooses tool +args │  │
                │  └─────────┬──────────┘  │
                │            │ tool_call    │
                │            ▼              │
                │   _execute_tool()         │
                └───────┬─────┬─────┬───────┘
                        │     │     │
            ┌───────────┘     │     └───────────┐
            ▼                 ▼                 ▼
   search_listings()   suggest_outfit()   create_fit_card()   ← tools.py
   (local dataset)     (Groq LLM)         (Groq LLM)
```

- **Trigger for each tool:** the LLM decides, turn by turn, with `tool_choice="auto"`.
- **State flow:** `_execute_tool()` writes each result into the `session` dict and
  appends a summary to the `messages` list the model reads next turn.
- **Error branches:** empty search results, API failures, and hitting `MAX_STEPS`
  all converge on `session["error"]`, which `app.py` surfaces to the user.

---

## AI Tool Plan

I used Claude Code to implement functions in `agent.py` and `tools.py`, to write
and run the tests, and to handle edge cases.

**Milestone 3 — Individual tool implementations:**
I gave Claude each tool's spec from the Tools section above (inputs, return value,
failure mode) and the data-loader helpers, and asked it to implement
`search_listings`, `suggest_outfit`, and `create_fit_card` in `tools.py`. I verified
each against the tests in `tests/test_tools.py` before wiring them into the agent.

**Milestone 4 — Planning loop and state management:**
I gave Claude this Planning Loop and State Management section plus the architecture
diagram and asked it to implement the LLM-driven loop in `run_agent()` using Groq
tool-calling: the model chooses tools via `TOOL_SCHEMAS`, `_execute_tool()` runs
them and updates the `session` dict, and the loop continues until the model stops
or `MAX_STEPS` is reached. I verified by running the happy-path and no-results
queries and confirming `app.py` still reads the same session fields.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — LLM reads the query and decides to search.**
`run_agent()` seeds `messages` with the system prompt + the user query and calls the
Groq model with the tool schemas. The model chooses `search_listings` with
`{"description": "vintage graphic tee", "max_price": 30}`. `_execute_tool()` runs the
search, stores the matches in `session["search_results"]`, sets `selected_item` to the
top result, and returns a JSON summary (ids, titles, prices) back to the model.

**Step 2 — LLM sees the results and decides to style one.**
Having the search summary in `messages`, the model calls `suggest_outfit` (optionally
with the `item_id` of the listing it likes best). `_execute_tool()` pulls that listing
and the user's wardrobe from `session` and calls the tool, which returns outfit ideas
(e.g. pairing the tee with the user's baggy jeans and chunky sneakers). The text is
stored in `session["outfit_suggestion"]` and fed back to the model.

**Step 3 — LLM writes the fit card.**
The model calls `create_fit_card`. `_execute_tool()` uses the stored `selected_item`
and `outfit_suggestion` to generate a caption, saves it to `session["fit_card"]`, and
returns it. On the next turn the model has nothing left to do, so it replies with a
short confirmation and **no tool call** — the loop ends.

**Final output to user:**
`app.py` reads the finished session and fills the three panels:
- **🛍️ Top listing found** — formatted details of `selected_item` (title, price, size, condition, platform, colors, brand, description).
- **👗 Outfit idea** — `session["outfit_suggestion"]`.
- **✨ Your fit card** — `session["fit_card"]`, ready to paste into a social post.

(No-results path: if `search_listings` returns nothing, the model skips the other
tools, `run_agent` sets `session["error"]`, and `app.py` shows that message in the
first panel with the other two left empty.)
