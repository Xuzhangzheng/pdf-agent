from src.config.settings import get_settings

from app.ui_quality import _interpret_metric


def test_interpret_passed():
    s = get_settings()
    assert "通过" in _interpret_metric("passed", True, s)


def test_interpret_table_blocks_fail():
    s = get_settings()
    text = _interpret_metric("table_blocks", 0, s)
    assert "未达标" in text
    assert str(s.min_table_blocks) in text
