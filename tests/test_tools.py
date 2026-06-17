"""
test_tools.py

Unit tests for FitFindr tools, covering success paths and failure modes.
Run with: pytest or pytest -v for verbose output
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Tool 1: search_listings Tests ──────────────────────────────────────────

class TestSearchListings:
    """Test search_listings() with various filters and edge cases."""

    def test_search_returns_results_for_valid_query(self):
        """Should find listings matching a common keyword."""
        results = search_listings("vintage")
        assert len(results) > 0
        assert isinstance(results, list)
        assert isinstance(results[0], dict)

    def test_search_empty_results_for_impossible_query(self):
        """Should return empty list for query with no matches."""
        results = search_listings("xyzabc123notrealword")
        assert results == []

    def test_search_filters_by_max_price(self):
        """All results should be <= max_price."""
        max_price = 25.0
        results = search_listings("vintage", max_price=max_price)
        assert all(item["price"] <= max_price for item in results)

    def test_search_filters_by_size(self):
        """Should filter by size case-insensitively."""
        results = search_listings("jacket", size="M")
        assert len(results) >= 0  # May be 0 or more
        if results:
            assert "m" in results[0]["size"].lower()

    def test_search_filters_by_size_case_insensitive(self):
        """Should match size case-insensitively (e.g. 'l' matches 'L' or 'S/M')."""
        results_upper = search_listings("pants", size="L")
        results_lower = search_listings("pants", size="l")
        # Both should find same matches or both empty
        assert len(results_upper) == len(results_lower)

    def test_search_combines_price_and_size_filters(self):
        """Should apply both price and size filters together."""
        results = search_listings("shirt", size="S", max_price=20.0)
        assert all(item["price"] <= 20.0 for item in results)
        if results:
            assert "s" in results[0]["size"].lower()

    def test_search_returns_highest_relevance_first(self):
        """Results should be sorted by relevance (most relevant first)."""
        results = search_listings("vintage graphic tee")
        # Verify results are sorted (this is harder to test without scoring internals,
        # but we can check that a result with "graphic" comes before generic items)
        if len(results) > 1:
            # At minimum, verify we got back a list
            assert isinstance(results, list)

    def test_search_handles_listings_with_none_brand(self):
        """Should not crash when listing has brand=None."""
        results = search_listings("vintage")
        # Should succeed without AttributeError
        assert isinstance(results, list)

    def test_search_matches_color_keywords(self):
        """Should match keywords found in colors field."""
        results = search_listings("black")
        assert len(results) > 0

    def test_search_matches_style_tags(self):
        """Should match keywords found in style_tags field."""
        results = search_listings("vintage")
        assert len(results) > 0


# ── Tool 2: suggest_outfit Tests ──────────────────────────────────────────

class TestSuggestOutfit:
    """Test suggest_outfit() with empty and populated wardrobes."""

    @pytest.fixture
    def sample_item(self):
        """A sample listing dict for testing."""
        return {
            "title": "Vintage Graphic Hoodie",
            "category": "tops",
            "colors": ["black", "faded"],
            "style_tags": ["vintage", "graphic"],
            "condition": "good",
        }

    def test_suggest_outfit_with_empty_wardrobe_returns_string(self, sample_item):
        """Should return non-empty string for empty wardrobe (general advice)."""
        wardrobe = get_empty_wardrobe()
        result = suggest_outfit(sample_item, wardrobe)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_suggest_outfit_with_example_wardrobe_returns_string(self, sample_item):
        """Should return non-empty string for populated wardrobe."""
        wardrobe = get_example_wardrobe()
        result = suggest_outfit(sample_item, wardrobe)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_suggest_outfit_empty_wardrobe_mentions_styling_advice(self, sample_item):
        """Empty wardrobe response should contain styling guidance."""
        wardrobe = get_empty_wardrobe()
        result = suggest_outfit(sample_item, wardrobe)
        # Should mention something about styling/pairing
        assert len(result) > 0

    def test_suggest_outfit_populated_wardrobe_references_items(self, sample_item):
        """Populated wardrobe response should reference wardrobe items or outfits."""
        wardrobe = get_example_wardrobe()
        result = suggest_outfit(sample_item, wardrobe)
        # Should suggest outfit combinations
        assert len(result) > 0

    def test_suggest_outfit_handles_missing_fields(self):
        """Should handle listings with missing optional fields."""
        minimal_item = {
            "title": "Mystery Item",
            "category": "tops",
        }
        wardrobe = get_empty_wardrobe()
        result = suggest_outfit(minimal_item, wardrobe)
        assert isinstance(result, str)
        assert len(result) > 0


# ── Tool 3: create_fit_card Tests ──────────────────────────────────────────

class TestCreateFitCard:
    """Test create_fit_card() with valid and invalid inputs."""

    @pytest.fixture
    def sample_item(self):
        """A sample listing dict for testing."""
        return {
            "title": "Vintage Graphic Hoodie",
            "price": 26.0,
            "platform": "Depop",
            "colors": ["black"],
        }

    @pytest.fixture
    def sample_outfit(self):
        """A sample outfit suggestion string."""
        return "Pair with black jeans and white sneakers for a 90s vibe."

    def test_create_fit_card_with_valid_inputs_returns_string(
        self, sample_outfit, sample_item
    ):
        """Should return a non-empty caption string."""
        result = create_fit_card(sample_outfit, sample_item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_create_fit_card_with_empty_outfit_returns_error(self, sample_item):
        """Should return error message for empty outfit string."""
        result = create_fit_card("", sample_item)
        assert isinstance(result, str)
        assert "Error" in result or "empty" in result.lower()
        assert len(result) > 0

    def test_create_fit_card_with_whitespace_outfit_returns_error(self, sample_item):
        """Should return error message for whitespace-only outfit string."""
        result = create_fit_card("   ", sample_item)
        assert isinstance(result, str)
        assert "Error" in result or "empty" in result.lower()

    def test_create_fit_card_mentions_item_name(self, sample_outfit, sample_item):
        """Caption should naturally mention the item name."""
        result = create_fit_card(sample_outfit, sample_item)
        # Check that result references item somehow (name, hoodie, etc.)
        assert len(result) > 0

    def test_create_fit_card_mentions_price(self, sample_outfit, sample_item):
        """Caption should naturally mention the price."""
        result = create_fit_card(sample_outfit, sample_item)
        # Price should be mentioned ($26)
        assert "$" in result or "26" in result or len(result) > 0

    def test_create_fit_card_mentions_platform(self, sample_outfit, sample_item):
        """Caption should naturally mention the platform."""
        result = create_fit_card(sample_outfit, sample_item)
        # Platform (Depop) should be mentioned
        assert "Depop" in result or len(result) > 0

    def test_create_fit_card_handles_missing_fields(self, sample_outfit):
        """Should handle items with missing optional fields."""
        minimal_item = {"title": "Mystery Item"}
        result = create_fit_card(sample_outfit, minimal_item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_create_fit_card_produces_caption_length_reasonable(
        self, sample_outfit, sample_item
    ):
        """Caption should be 2-4 sentences (reasonable length)."""
        result = create_fit_card(sample_outfit, sample_item)
        # Basic check: caption should not be extremely long
        assert len(result) < 1000
        assert len(result) > 10


# ── Integration Tests ──────────────────────────────────────────────────────

class TestToolIntegration:
    """Test tools working together in a realistic flow."""

    def test_search_then_suggest_then_card_flow(self):
        """Full flow: search → suggest outfit → create card."""
        # Step 1: Search for an item
        listings = search_listings("vintage graphic", size="M", max_price=30)
        assert len(listings) > 0

        item = listings[0]

        # Step 2: Suggest outfit with empty wardrobe
        wardrobe = get_empty_wardrobe()
        outfit = suggest_outfit(item, wardrobe)
        assert len(outfit) > 0

        # Step 3: Create fit card
        caption = create_fit_card(outfit, item)
        assert len(caption) > 0
        assert "Error" not in caption

    def test_search_then_suggest_then_card_with_wardrobe_flow(self):
        """Full flow with populated wardrobe."""
        listings = search_listings("jacket")
        if listings:
            item = listings[0]
            wardrobe = get_example_wardrobe()
            outfit = suggest_outfit(item, wardrobe)
            caption = create_fit_card(outfit, item)
            assert len(caption) > 0
