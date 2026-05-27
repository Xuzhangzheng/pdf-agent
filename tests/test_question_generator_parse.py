from src.indexing.question_generator import extract_questions_from_llm_text


def test_extract_valid_json_array():
    raw = '["平键半圆部分能否不倒角？", "3.7条对倒角有何规定？"]'
    qs = extract_questions_from_llm_text(raw)
    assert len(qs) == 2
    assert "3.7" in qs[1]


def test_extract_json_with_markdown_fence():
    raw = '```json\n["问题一", "问题二"]\n```'
    qs = extract_questions_from_llm_text(raw)
    assert qs == ["问题一", "问题二"]


def test_extract_malformed_array_by_bracket_slice():
    raw = '说明如下：["键表面有何要求？", "3.2 不允许裂纹"] 结束'
    qs = extract_questions_from_llm_text(raw)
    assert len(qs) >= 2


def test_extract_quoted_strings_fallback():
    raw = '无效前缀 "半圆键圆弧是否允许不倒角" 后缀'
    qs = extract_questions_from_llm_text(raw)
    assert any("半圆键" in q for q in qs)
