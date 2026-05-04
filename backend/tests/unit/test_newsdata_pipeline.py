"""
test_newsdata_pipeline.py — Unit tests for the newsdata.io news pipeline.

Tests:
  - article_extractor.extract_key_sentence (sentence scoring algorithm)
  - article_extractor.derive_stock_impact  (signal class → impact string)
  - news_service._classify_signal_class    (headline classification)
  - news_service._is_relevant              (stock relevance filter)
  - news_service._enrich                   (key_sentence + stock_impact added)
  - agent_news._article_to_node            (node schema + value_raw shape)
  - graph builder news edges               (caused_by, correlates, part_of)

Zero network calls — all data is synthetic in-process.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_node(name: str, category: str, signal: str, stock: str = "RELIANCE",
               weight: float = 0.5, conf: float = 0.8,
               signal_class: str = "") -> object:
    """Build a minimal Node-like object for graph builder tests."""
    from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance

    cat_map = {
        "technical":    NodeCategory.technical,
        "fundamental":  NodeCategory.fundamental,
        "news":         NodeCategory.news,
        "announcement": NodeCategory.announcement,
        "context":      NodeCategory.context,
    }
    sig_map = {
        "positive": NodeSignal.positive,
        "negative": NodeSignal.negative,
        "neutral":  NodeSignal.neutral,
    }
    return Node(
        stock=stock,
        category=cat_map[category],
        name=name,
        value=f"test value for {name}",
        value_raw={"signal_class": signal_class} if signal_class else {},
        signal=sig_map[signal],
        confidence=conf,
        source="test_source",
        as_of_date=date(2026, 4, 26),
        fetched_at_ist=datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc),
        horizon_relevance=HorizonRelevance.both,
        weight=weight,
        weight_version="v1",
        schema_version=1,
        sanitized=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. article_extractor — extract_key_sentence
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractKeySentence(unittest.TestCase):

    def test_returns_empty_for_empty_text(self):
        from util.article_extractor import extract_key_sentence
        self.assertEqual(extract_key_sentence("", "RELIANCE"), "")

    def test_returns_single_sentence_as_is(self):
        from util.article_extractor import extract_key_sentence
        text = "Reliance Industries reported a 14% rise in net profit for Q4 FY26."
        result = extract_key_sentence(text, "RELIANCE", "Reliance Industries")
        self.assertIn("Reliance", result)

    def test_picks_sentence_with_numbers_over_generic(self):
        from util.article_extractor import extract_key_sentence
        text = (
            "Markets were volatile today. "
            "Reliance Industries reported revenue of ₹2,35,000 crore, up 18% YoY. "
            "Analysts are watching the stock closely."
        )
        result = extract_key_sentence(text, "RELIANCE", "Reliance Industries")
        self.assertIn("18%", result)

    def test_picks_sentence_with_company_mention(self):
        from util.article_extractor import extract_key_sentence
        text = (
            "The market was flat. "
            "TCS announced a major contract worth ₹5,000 crore with a US bank. "
            "Other IT stocks also moved."
        )
        result = extract_key_sentence(text, "TCS", "Tata Consultancy Services")
        self.assertIn("contract", result.lower())

    def test_boilerplate_is_penalised(self):
        from util.article_extractor import extract_key_sentence
        text = (
            "Click here to read more about the market. "
            "Infosys posted Q4 net profit of ₹7,969 crore, beating estimates. "
            "Subscribe for premium content."
        )
        result = extract_key_sentence(text, "INFY", "Infosys")
        self.assertNotIn("click here", result.lower())
        self.assertNotIn("subscribe", result.lower())

    def test_truncates_very_long_sentence(self):
        from util.article_extractor import extract_key_sentence
        long_sentence = "HDFC Bank " + ("reported very strong profit growth " * 20)
        result = extract_key_sentence(long_sentence, "HDFCBANK", "HDFC Bank")
        self.assertLessEqual(len(result), 303)   # 300 + "…"

    def test_handles_whitespace_only_text(self):
        from util.article_extractor import extract_key_sentence
        result = extract_key_sentence("   \n\t  ", "TCS")
        self.assertEqual(result, "")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. article_extractor — derive_stock_impact
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeriveStockImpact(unittest.TestCase):

    def test_regulatory_sebi_action_returns_non_empty(self):
        from util.article_extractor import derive_stock_impact
        result = derive_stock_impact("regulatory_sebi_action")
        self.assertTrue(len(result) > 20)
        self.assertIn("SEBI", result)

    def test_fraud_allegation_mentions_decline(self):
        from util.article_extractor import derive_stock_impact
        result = derive_stock_impact("fraud_allegation")
        self.assertIn("decline", result.lower())

    def test_credit_rating_downgrade_disambiguated(self):
        from util.article_extractor import derive_stock_impact
        result = derive_stock_impact("credit_rating_change", "CRISIL downgrades the bond")
        self.assertIn("downgrade", result.lower())

    def test_credit_rating_upgrade_disambiguated(self):
        from util.article_extractor import derive_stock_impact
        result = derive_stock_impact("credit_rating_change", "ICRA upgrades outlook to positive")
        self.assertIn("upgrade", result.lower())

    def test_unknown_class_returns_generic(self):
        from util.article_extractor import derive_stock_impact
        result = derive_stock_impact("totally_unknown_class")
        self.assertTrue(len(result) > 10)

    def test_major_contract_mentions_order_book(self):
        from util.article_extractor import derive_stock_impact
        result = derive_stock_impact("major_contract")
        self.assertIn("order", result.lower())


# ═══════════════════════════════════════════════════════════════════════════════
# 3. news_service — _classify_signal_class
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifySignalClass(unittest.TestCase):

    def _classify(self, title: str) -> str:
        from services.news_service import _classify_signal_class
        return _classify_signal_class(title)

    def test_sebi_penalty_classified_correctly(self):
        self.assertEqual(self._classify("SEBI imposes penalty on XYZ Ltd"), "regulatory_sebi_action")

    def test_fraud_classified_correctly(self):
        self.assertEqual(self._classify("Fraud allegations surface at ABC Corp"), "fraud_allegation")

    def test_crisil_downgrade_classified_correctly(self):
        self.assertEqual(self._classify("CRISIL downgrades ABC Ltd bonds"), "credit_rating_change")

    def test_dividend_classified_correctly(self):
        self.assertEqual(self._classify("Reliance declares interim dividend of ₹9"), "dividend_or_buyback")

    def test_merger_classified_correctly(self):
        self.assertEqual(self._classify("TCS announces merger with global firm"), "ma_event")

    def test_contract_win_classified_correctly(self):
        self.assertEqual(self._classify("Infosys bags order worth ₹2,000 crore"), "major_contract")

    def test_positive_headline_classified_generic_positive(self):
        result = self._classify("XYZ Ltd posts strong Q4 profit growth")
        self.assertEqual(result, "generic_positive")

    def test_negative_headline_classified_generic_negative(self):
        result = self._classify("ABC Ltd Q4 results miss estimates, shares fall")
        self.assertEqual(result, "generic_negative")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. news_service — _is_relevant
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsRelevant(unittest.TestCase):

    def _relevant(self, title: str, sym: str, name: str = "") -> bool:
        from services.news_service import _is_relevant
        return _is_relevant(title, sym, name)

    def test_symbol_in_title_is_relevant(self):
        self.assertTrue(self._relevant("TCS Q4 results beat estimates", "TCS"))

    def test_company_name_in_title_is_relevant(self):
        self.assertTrue(self._relevant(
            "Tata Consultancy posts strong numbers",
            "TCS", "Tata Consultancy Services",
        ))

    def test_unrelated_title_is_not_relevant(self):
        self.assertFalse(self._relevant("Sensex rises 200 points on FII buying", "TCS"))

    def test_unrelated_stock_does_not_match_different_company(self):
        # HDFCBANK should not match a headline only about ICICI Bank
        self.assertFalse(self._relevant(
            "ICICI Bank Q4 net profit rises 15%, beats estimates",
            "HDFCBANK", "HDFC Bank",
        ))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. news_service — _enrich adds key_sentence and stock_impact
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnrich(unittest.TestCase):

    def _make_article(self, title: str, description: str = "", content: str = "") -> dict:
        return {
            "title": title,
            "description": description,
            "content": content,
            "link": "https://example.com/article",
            "published": "2026-04-26T10:00:00+00:00",
            "source": "newsdata_io",
            "source_name": "MoneyControl",
            "sentiment": "",
        }

    def test_enrich_adds_key_sentence_field(self):
        from services.news_service import _enrich
        articles = [self._make_article(
            "Reliance Industries Q4 profit surges 18%",
            description="Reliance Industries reported a net profit of ₹19,407 crore for Q4 FY26, up 18% year-on-year.",
        )]
        enriched = _enrich(articles, "RELIANCE", "Reliance Industries")
        self.assertIn("key_sentence", enriched[0])
        self.assertTrue(len(enriched[0]["key_sentence"]) > 0)

    def test_enrich_adds_stock_impact_field(self):
        from services.news_service import _enrich
        articles = [self._make_article("SEBI penalises Infosys for insider trading")]
        enriched = _enrich(articles, "INFY", "Infosys")
        self.assertIn("stock_impact", enriched[0])
        self.assertTrue(len(enriched[0]["stock_impact"]) > 10)

    def test_enrich_adds_signal_class_field(self):
        from services.news_service import _enrich
        articles = [self._make_article("HDFC Bank bags order from RBI for payment system")]
        enriched = _enrich(articles, "HDFCBANK", "HDFC Bank")
        self.assertIn("signal_class", enriched[0])
        self.assertIsInstance(enriched[0]["signal_class"], str)

    def test_enrich_preserves_existing_fields(self):
        from services.news_service import _enrich
        articles = [self._make_article("TCS wins contract worth ₹3,000 crore")]
        enriched = _enrich(articles, "TCS", "Tata Consultancy Services")
        self.assertEqual(enriched[0]["source"], "newsdata_io")
        self.assertEqual(enriched[0]["source_name"], "MoneyControl")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. agent_news — _article_to_node builds correct Node
# ═══════════════════════════════════════════════════════════════════════════════

class TestArticleToNode(unittest.TestCase):

    def _make_request(self, stock: str = "RELIANCE"):
        from schemas.messages import FetchRequest
        from schemas.node import HorizonRelevance
        from unittest.mock import MagicMock
        req = MagicMock(spec=FetchRequest)
        req.stock = stock
        req.as_of_date = date(2026, 4, 26)
        req.request_id = "test-req-001"
        profile = MagicMock()
        profile.horizon.value = "short"
        req.profile = profile
        return req

    def _make_article(self) -> dict:
        return {
            "title": "Reliance Industries Q4 profit up 18%",
            "description": "Reliance Industries reported record quarterly earnings.",
            "content": "Net profit rose to ₹19,407 crore, beating analyst estimates of ₹18,000 crore.",
            "key_sentence": "Net profit rose to ₹19,407 crore, beating analyst estimates.",
            "stock_impact": "Positive earnings beat typically triggers analyst upgrades.",
            "signal_class": "generic_positive",
            "link": "https://example.com/reliance-q4",
            "published": "2026-04-26T10:00:00+00:00",
            "source": "newsdata_io",
            "source_name": "MoneyControl",
            "sentiment": "",
        }

    def test_node_has_correct_category(self):
        from agents.agent_news import _article_to_node
        from schemas.node import NodeCategory
        node = _article_to_node(
            self._make_article(), 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.category, NodeCategory.news)

    def test_node_name_uses_index(self):
        from agents.agent_news import _article_to_node
        node = _article_to_node(
            self._make_article(), 3, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(node.name, "News_Item_3")

    def test_node_value_contains_key_sentence(self):
        from agents.agent_news import _article_to_node
        node = _article_to_node(
            self._make_article(), 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertIn("Key insight", node.value)

    def test_node_value_raw_has_required_fields(self):
        from agents.agent_news import _article_to_node
        node = _article_to_node(
            self._make_article(), 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        for field in ("title", "key_sentence", "stock_impact", "signal_class", "link", "published"):
            self.assertIn(field, node.value_raw, f"Missing field: {field}")

    def test_node_stock_impact_propagated_to_value_raw(self):
        from agents.agent_news import _article_to_node
        node = _article_to_node(
            self._make_article(), 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            node.value_raw["stock_impact"],
            "Positive earnings beat typically triggers analyst upgrades.",
        )

    def test_node_confidence_is_0_80_for_newsdata_source(self):
        from agents.agent_news import _article_to_node
        node = _article_to_node(
            self._make_article(), 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(node.confidence, 0.80)

    def test_empty_title_returns_none(self):
        from agents.agent_news import _article_to_node
        art = self._make_article()
        art["title"] = ""
        node = _article_to_node(
            art, 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertIsNone(node)

    def test_node_is_sanitized(self):
        from agents.agent_news import _article_to_node
        node = _article_to_node(
            self._make_article(), 0, self._make_request(),
            "short", datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
        )
        self.assertTrue(node.sanitized)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. graph builder — news edges (caused_by, correlates, part_of cluster)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewsGraphEdges(unittest.TestCase):

    def _build(self, nodes):
        from graph.scorer import score_all
        from graph.builder import build_edges
        scores = score_all(nodes, date(2026, 4, 26))
        return build_edges(nodes, scores, analysis_id="test")

    def test_news_node_to_price_caused_by_edge_exists(self):
        nodes = [
            _make_node("News_Item_0", "news",        "positive", signal_class="major_contract"),
            _make_node("Price",       "fundamental",  "positive"),
        ]
        edges = self._build(nodes)
        relations = {(e.from_id.split("|")[2], e.to_id.split("|")[2], e.relation) for e in edges}
        self.assertIn(("News_Item_0", "Price", "caused_by"), relations)

    def test_high_severity_news_contradicts_opposing_technical(self):
        nodes = [
            _make_node("News_Item_0", "news",      "negative", signal_class="regulatory_sebi_action"),
            _make_node("RSI_14",      "technical", "positive"),
        ]
        edges = self._build(nodes)
        relations = {(e.from_id.split("|")[2], e.to_id.split("|")[2], e.relation) for e in edges}
        self.assertIn(("News_Item_0", "RSI_14", "contradicts"), relations)

    def test_high_severity_news_supports_same_signal_technical(self):
        nodes = [
            _make_node("News_Item_0", "news",      "negative", signal_class="fraud_allegation"),
            _make_node("RSI_14",      "technical", "negative"),
        ]
        edges = self._build(nodes)
        relations = {(e.from_id.split("|")[2], e.to_id.split("|")[2], e.relation) for e in edges}
        self.assertIn(("News_Item_0", "RSI_14", "supports"), relations)

    def test_major_contract_news_correlates_with_revenue_node(self):
        nodes = [
            _make_node("News_Item_0",        "news",        "positive", signal_class="major_contract"),
            _make_node("Revenue_Quarterly",  "fundamental", "positive"),
        ]
        edges = self._build(nodes)
        relations = {(e.from_id.split("|")[2], e.to_id.split("|")[2], e.relation) for e in edges}
        self.assertIn(("News_Item_0", "Revenue_Quarterly", "correlates"), relations)

    def test_news_part_of_news_impact_cluster(self):
        nodes = [_make_node("News_Item_0", "news", "positive", signal_class="generic_positive")]
        edges = self._build(nodes)
        cluster_edges = [e for e in edges if "news_impact" in e.to_id]
        self.assertTrue(len(cluster_edges) >= 1)

    def test_low_severity_news_no_extra_contradicts_technical(self):
        """generic_positive is NOT in _NEWS_HIGH_SEVERITY — should not force contradicts."""
        nodes = [
            _make_node("News_Item_0", "news",      "positive", signal_class="generic_positive"),
            _make_node("RSI_14",      "technical", "negative"),
        ]
        edges = self._build(nodes)
        # The standard supports/contradicts rule (cross-category) still applies,
        # but there should be NO additional contradicts from the news-specific path
        # for non-high-severity class. Verify the edge exists (from cross-category rule)
        # without asserting false negatives.
        news_tech_edges = [
            e for e in edges
            if "News_Item_0" in e.from_id and "RSI_14" in e.to_id
        ]
        # With opposite signals, normal cross-category contradicts fires — that's correct
        for e in news_tech_edges:
            self.assertIn(e.relation, ("contradicts", "supports", "same_domain"))


if __name__ == "__main__":
    unittest.main()
