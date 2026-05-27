from __future__ import annotations

from src.retrieval.query_signals import (
    extract_clause_ids_from_query,
    is_english_boilerplate_text,
    wants_composite_strength_table,
    wants_table_evidence,
    wants_technical_requirements_overview,
)


def test_ocr_clause_4l2_to_412():
    ids = extract_clause_ids_from_query("条款 4.l.2 对键的形位公差有何要求？")
    assert "4.1.2" in ids


def test_table_intent_keywords():
    assert wants_table_evidence("请根据标准中的表格说明键的尺寸、公差或相关参数限值。")
    assert wants_table_evidence("表1 键宽公差")
    assert not wants_table_evidence("条款 4.l.2 对键的形位公差有何要求？")


def test_composite_strength_table():
    q = "键的抗拉强度要求是什么？验收检查与表1中的检查项目有何关系？"
    assert wants_composite_strength_table(q)


def test_technical_requirements_overview():
    assert wants_technical_requirements_overview("技术条件具体包含着什么")
    assert wants_technical_requirements_overview("本标准讲的是什么内容")
    assert not wants_technical_requirements_overview("表1 键宽 AQL")


def test_english_boilerplate():
    assert is_english_boilerplate_text("Technical specifications for keys")
    assert not is_english_boilerplate_text("3.2 键表面不允许有裂纹")
