"""
agent.py

The FitFindr agentic loop. Uses a Groq LLM to dynamically decide which tool to
call next, based on the user query and the results of previous tool calls.

The loop is genuinely LLM-driven: each turn we send the conversation plus the
tool schemas to the model, and the model chooses which tool to call (or decides
it is finished). The model picks the tool and its *simple* arguments (search
terms, which listing to style); the executor injects the heavy objects
(the user's wardrobe, the selected listing dict) from session state.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    _get_groq_client,
)


# ── configuration ─────────────────────────────────────────────────────────────

MODEL = "llama-3.3-70b-versatile"
MAX_STEPS = 8  # safety cap on planning-loop iterations


# ── tool registry (schemas the LLM sees) ───────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": (
                "Search secondhand clothing listings. Call this FIRST to find "
                "items matching the user's request. Returns a list of matching "
                "listings (with ids) or an empty list if nothing matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Keywords describing the item, e.g. 'vintage graphic tee'.",
                    },
                    "size": {
                        "type": "string",
                        "description": "Size to filter by (e.g. 'M'). Omit if the user didn't specify.",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price in dollars. Omit if the user didn't specify.",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_outfit",
            "description": (
                "Suggest how to style one listing with the user's wardrobe. "
                "Only call after search_listings returned at least one result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": (
                            "The id of the listing to style. Omit to use the "
                            "top (best-matching) result."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_fit_card",
            "description": (
                "Write a shareable social-media caption for the styled outfit. "
                "Only call after suggest_outfit has produced a suggestion."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


SYSTEM_PROMPT = (
    "You are FitFindr, an agent that helps users find secondhand clothing and "
    "style it. You have three tools: search_listings, suggest_outfit, and "
    "create_fit_card.\n\n"
    "Complete the user's request by calling tools in a sensible order:\n"
    "1. search_listings to find matching items.\n"
    "2. If (and only if) there are results, suggest_outfit to style the best one.\n"
    "3. create_fit_card to write a caption for that outfit.\n\n"
    "If search_listings returns no results, do NOT call the other tools. Instead "
    "reply with a short, helpful message telling the user what to try differently.\n\n"
    "When you have created the fit card, reply with a brief confirmation and stop."
)


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # args the LLM passed to search_listings
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # listing chosen for suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "messages": [],              # conversation history for LLM
        "tool_calls": [],            # names of tools executed during this run
    }


# ── tool executor ──────────────────────────────────────────────────────────────

def _execute_tool(name: str, args: dict, session: dict) -> str:
    """
    Run the tool the LLM chose, update session state, and return a short string
    result to feed back to the model.

    The LLM supplies only simple arguments; the heavy objects (wardrobe, the
    selected listing dict) are pulled from `session` here so the model never has
    to round-trip them.
    """
    if name == "search_listings":
        description = args.get("description", session["query"])
        size = args.get("size")
        max_price = args.get("max_price")
        session["parsed"] = {
            "description": description,
            "size": size,
            "max_price": max_price,
        }
        results = search_listings(description, size, max_price)
        session["search_results"] = results

        if not results:
            return json.dumps({"count": 0, "results": []})

        # Default the selection to the top result; suggest_outfit may override.
        session["selected_item"] = results[0]
        summary = [
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "price": r.get("price"),
                "size": r.get("size"),
                "brand": r.get("brand"),
            }
            for r in results[:10]
        ]
        return json.dumps({"count": len(results), "results": summary})

    if name == "suggest_outfit":
        results = session["search_results"]
        if not results:
            return "Error: no listings have been found yet. Call search_listings first."

        item = session["selected_item"] or results[0]
        item_id = args.get("item_id")
        if item_id is not None:
            match = next((r for r in results if str(r.get("id")) == str(item_id)), None)
            if match is not None:
                item = match
        session["selected_item"] = item

        suggestion = suggest_outfit(item, session["wardrobe"])
        session["outfit_suggestion"] = suggestion
        return suggestion

    if name == "create_fit_card":
        item = session["selected_item"]
        outfit = session["outfit_suggestion"]
        if not item or not outfit:
            return "Error: style an outfit with suggest_outfit before creating a fit card."

        card = create_fit_card(outfit, item)
        session["fit_card"] = card
        return card

    return f"Error: unknown tool '{name}'."


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    The loop is LLM-driven: on each turn the model is given the conversation and
    the tool schemas, and it decides which tool to call next (or to stop). We
    execute its chosen tool, append the result, and repeat until the model stops
    calling tools or we hit MAX_STEPS.
    """
    session = _new_session(query, wardrobe)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    session["messages"] = messages

    client = _get_groq_client()
    final_text = None

    try:
        for _ in range(MAX_STEPS):
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            msg = response.choices[0].message

            # Record the assistant turn (preserving any tool calls) so the model
            # sees its own decisions on the next iteration.
            assistant_msg = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            # No tool calls → the model is done and `content` is its final reply.
            if not msg.tool_calls:
                final_text = msg.content
                break

            # Execute each tool the model chose and feed results back.
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}

                result = _execute_tool(name, tool_args, session)
                session["tool_calls"].append(name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": result,
                    }
                )
    except Exception as exc:  # network / API / SDK failures
        session["error"] = f"The agent could not complete the request: {exc}"
        return session

    # Decide success vs. error from what actually got produced. app.py relies on
    # session["error"] being set whenever the happy-path fields are missing.
    if session["fit_card"] is None:
        if not session["search_results"]:
            parsed = session["parsed"]
            desc = parsed.get("description") or query
            session["error"] = (
                final_text
                or f"No listings found matching '{desc}'. Try a different search."
            )
        else:
            session["error"] = (
                final_text
                or "The agent stopped before producing a fit card. Please try again."
            )

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
