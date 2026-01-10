"""Tests for cleanup categories."""

import pytest

from uncruft.categories import (
    CATEGORIES,
    get_all_categories,
    get_category,
    get_review_categories,
    get_safe_categories,
)
from uncruft.models import RiskLevel


class TestCategories:
    def test_categories_not_empty(self):
        assert len(CATEGORIES) > 0

    def test_all_categories_have_required_fields(self):
        for cat_id, cat in CATEGORIES.items():
            assert cat.id == cat_id
            assert cat.name
            # Recursive categories use glob_patterns, regular categories use paths
            if cat.is_recursive:
                assert len(cat.glob_patterns) > 0, f"{cat_id} is recursive but has no glob_patterns"
                assert len(cat.search_roots) > 0, f"{cat_id} is recursive but has no search_roots"
            else:
                assert len(cat.paths) > 0, f"{cat_id} has no paths"
            assert cat.risk_level in RiskLevel
            assert cat.description
            assert cat.consequences
            assert cat.recovery

    def test_get_category_exists(self):
        cat = get_category("npm_cache")
        assert cat is not None
        assert cat.id == "npm_cache"

    def test_get_category_not_exists(self):
        cat = get_category("nonexistent_category")
        assert cat is None

    def test_get_all_categories(self):
        cats = get_all_categories()
        assert len(cats) == len(CATEGORIES)

    def test_get_safe_categories(self):
        safe = get_safe_categories()
        for cat in safe:
            assert cat.risk_level == RiskLevel.SAFE

    def test_get_review_categories(self):
        review = get_review_categories()
        for cat in review:
            assert cat.risk_level == RiskLevel.REVIEW

    def test_conda_cache_is_safe(self):
        cat = get_category("conda_cache")
        assert cat is not None
        assert cat.risk_level == RiskLevel.SAFE

    def test_docker_data_needs_review(self):
        cat = get_category("docker_data")
        assert cat is not None
        assert cat.risk_level == RiskLevel.REVIEW

    def test_paths_use_tilde(self):
        """Ensure paths use ~ notation for portability."""
        for cat in get_all_categories():
            for path in cat.paths:
                # Should not have hardcoded /Users/xxx paths
                assert not path.startswith("/Users/")

    def test_get_risky_categories(self):
        """Get risky categories (may be empty if none defined)."""
        from uncruft.categories import get_risky_categories
        risky = get_risky_categories()
        # Currently no risky categories are defined, so this should be empty
        for cat in risky:
            assert cat.risk_level == RiskLevel.RISKY
