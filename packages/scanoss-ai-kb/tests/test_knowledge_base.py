"""Tests for KnowledgeBase facade."""

import pytest
from scanoss_ai_kb import KnowledgeBase, Matcher


class TestKnowledgeBase:
    def test_init_creates_db(self, temp_db_path) -> None:
        kb = KnowledgeBase(db_path=temp_db_path)
        assert temp_db_path.exists()
        kb.close()

    def test_context_manager(self, temp_db_path) -> None:
        with KnowledgeBase(db_path=temp_db_path) as kb:
            assert kb.db is not None
            assert kb.matcher is not None

    def test_matcher_property(self, temp_db_path) -> None:
        with KnowledgeBase(db_path=temp_db_path) as kb:
            matcher = kb.matcher
            assert isinstance(matcher, Matcher)

    def test_db_property_after_close_raises(self, temp_db_path) -> None:
        kb = KnowledgeBase(db_path=temp_db_path)
        kb.close()
        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = kb.db

    def test_matcher_property_after_close_raises(self, temp_db_path) -> None:
        kb = KnowledgeBase(db_path=temp_db_path)
        kb.close()
        with pytest.raises(RuntimeError, match="Matcher not initialized"):
            _ = kb.matcher

    def test_version_after_init(self, temp_db_path) -> None:
        with KnowledgeBase(db_path=temp_db_path) as kb:
            # Should be initialized with schema version 1
            assert kb.db.get_version() == 1
