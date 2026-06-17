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

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


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

    # Filter by price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Filter by size (case-insensitive)
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Score listings by keyword relevance
    keywords = set(description.lower().split())
    scored_listings = []

    for listing in listings:
        score = 0

        # Search in various fields with different weights
        searchable_text = {
            "title": (listing.get("title", ""), 3),
            "description": (listing.get("description", ""), 2),
            "category": (listing.get("category", ""), 2),
            "brand": (listing.get("brand") or "", 2),
        }

        for field, (text, weight) in searchable_text.items():
            field_words = set(text.lower().split())
            matches = len(keywords & field_words)
            score += matches * weight

        # Search in lists
        for tag in listing.get("style_tags", []):
            if tag.lower() in keywords:
                score += 2

        for color in listing.get("colors", []):
            if color.lower() in keywords:
                score += 1

        if score > 0:
            scored_listings.append((score, listing))

    # Sort by score descending and return listing dicts
    scored_listings.sort(key=lambda x: x[0], reverse=True)
    return [listing for score, listing in scored_listings]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

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
    client = _get_groq_client()

    # Format new item details
    item_details = f"""
Item: {new_item.get('title', 'Unknown')}
Category: {new_item.get('category', 'N/A')}
Colors: {', '.join(new_item.get('colors', []))}
Style tags: {', '.join(new_item.get('style_tags', []))}
Condition: {new_item.get('condition', 'N/A')}
"""

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe: general styling advice
        prompt = f"""You are a fashion styling assistant. Given this thrifted piece, suggest 1-2 outfit ideas by describing what types of items would pair well with it.

{item_details}

Provide practical styling advice mentioning:
- What types of tops/bottoms/shoes/accessories would work well
- The overall vibe or occasions it suits
- Color palette suggestions

Keep your response friendly and concise (2-3 sentences per outfit idea)."""
    else:
        # Non-empty wardrobe: specific outfit combinations
        wardrobe_text = "\n".join(
            [
                f"- {item.get('name', 'Unknown')}: {item.get('category', 'N/A')} "
                f"({', '.join(item.get('colors', []))})"
                for item in wardrobe_items
            ]
        )

        prompt = f"""You are a fashion styling assistant. Given this thrifted piece and the user's wardrobe, suggest 1-2 complete outfit combinations.

New item to style:
{item_details}

User's wardrobe items:
{wardrobe_text}

Suggest specific outfit combinations by naming pieces from the wardrobe that go well with the new item. For each outfit:
- List the pieces (reference them by name)
- Explain why they work together
- Mention the overall look/vibe

Keep your response friendly and concise."""

    message = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
    )

    return message.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

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
    # Guard against empty outfit
    if not outfit or not outfit.strip():
        return "Error: Could not generate a caption because outfit suggestions were empty. Please try again."

    client = _get_groq_client()

    item_name = new_item.get("title", "thrifted piece")
    price = new_item.get("price", "N/A")
    platform = new_item.get("platform", "thrift platform")
    colors = ", ".join(new_item.get("colors", []))

    prompt = f"""You are a social media expert creating authentic, casual OOTD (Outfit of the Day) captions for TikTok/Instagram.

Item details:
- Name: {item_name}
- Price: ${price}
- Platform: {platform}
- Colors: {colors}

Outfit suggestion:
{outfit}

Write a 2-4 sentence caption that:
- Sounds casual and authentic (like a real person, not a brand)
- Naturally mentions the item name, price, and platform once each
- Captures the outfit vibe with specific details
- Includes relevant emojis but stays authentic

Just write the caption, nothing else."""

    message = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=1.2,
    )

    return message.choices[0].message.content
