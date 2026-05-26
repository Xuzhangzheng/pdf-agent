from __future__ import annotations

from src.llm.ark_client import ArkClient


def test_parse_json_fixes_latex_backslash_in_string():
    raw = (
        '{"has_evidence":true,"hallucination_risk":"low","should_refuse":false,'
        '"unsupported_claims":[],"missing_citations":[],"critique":"含 \\geq 590",'
        '"action":"accept"}'
    )
    data = ArkClient.parse_json(raw)
    assert data["action"] == "accept"
    assert "geq" in data["critique"]


def test_parse_json_strips_markdown_fence():
    raw = '```json\n{"action":"accept","has_evidence":true}\n```'
    data = ArkClient.parse_json(raw)
    assert data["action"] == "accept"
