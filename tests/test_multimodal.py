"""
多模态模块单元测试
"""

import base64
import json
import pytest

from agent.multimodal.image_parser import (
    ParsedTicket,
    _parse_ticket_json,
    _parse_batch_json,
    _extract_json_from_text,
)
from agent.multimodal.multimodal_router import MultimodalRouter, MultimodalResult


class TestParsedTicket:
    def test_to_search_query(self):
        t = ParsedTicket(title="刹车异响", project="G08", pu="01/02", ecu="ESP")
        q = t.to_search_query()
        assert "刹车异响" in q
        assert "G08" in q
        assert "01/02" in q
        assert "ESP" in q

    def test_to_search_query_title_only(self):
        t = ParsedTicket(title="简单描述")
        assert t.to_search_query() == "简单描述"

    def test_to_dict(self):
        t = ParsedTicket(title="test", project="P1", confidence=0.8)
        d = t.to_dict()
        assert d["title"] == "test"
        assert d["project"] == "P1"
        assert d["confidence"] == 0.8
        assert "ecu" not in d  # None values excluded


class TestJsonParsing:
    def test_parse_single_ticket_json(self):
        raw = '{"title": "ESP故障", "project": "G08", "pu": "01/02", "confidence": 0.9}'
        ticket = _parse_ticket_json(raw)
        assert ticket.title == "ESP故障"
        assert ticket.project == "G08"
        assert ticket.pu == "01/02"
        assert ticket.confidence == 0.9

    def test_parse_ticket_with_markdown(self):
        raw = '```json\n{"title": "测试", "confidence": 0.7}\n```'
        ticket = _parse_ticket_json(raw)
        assert ticket.title == "测试"

    def test_parse_batch_json(self):
        raw = '[{"title": "t1", "confidence": 0.9}, {"title": "t2", "confidence": 0.8}]'
        tickets = _parse_batch_json(raw)
        assert len(tickets) == 2
        assert tickets[0].title == "t1"
        assert tickets[1].title == "t2"

    def test_parse_batch_filters_empty(self):
        raw = '[{"title": "t1"}, {"title": ""}]'
        tickets = _parse_batch_json(raw)
        assert len(tickets) == 1

    def test_extract_json_from_text(self):
        text = 'Here is the result: {"title": "test"} and some extra text'
        result = _extract_json_from_text(text)
        data = json.loads(result)
        assert data["title"] == "test"


class TestMultimodalRouter:
    def test_text_only(self):
        router = MultimodalRouter()
        result = router.process(text="ESP制动异响")
        assert result.source == "text"
        assert len(result.tickets) == 1
        assert result.tickets[0].title == "ESP制动异响"
        assert result.tickets[0].confidence == 1.0

    def test_empty_input(self):
        router = MultimodalRouter()
        result = router.process()
        assert result.source == "unknown"
        assert len(result.tickets) == 0

    def test_process_for_duplicate_search(self):
        router = MultimodalRouter()
        result = router.process_for_duplicate_search(text="刹车异响 PU01/02")
        assert result["success"] is True
        assert result["ticket_count"] == 1
        assert len(result["queries"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
