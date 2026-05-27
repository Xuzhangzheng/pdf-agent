from src.config.settings import Settings
from src.observability.langfuse_telemetry import (
    _sanitize_io,
    _truncate_value,
    prepare_langfuse_io,
)


def test_prepare_langfuse_io_disabled():
    s = Settings(langfuse_log_io=False)
    assert prepare_langfuse_io({"a": 1}, settings=s) is None


def test_truncate_string():
    assert _truncate_value("hello", max_chars=10) == "hello"
    long = "x" * 100
    out = _truncate_value(long, max_chars=20)
    assert len(out) > 20
    assert "truncated" in out


def test_sanitize_image_url():
    payload = [
        {
            "type": "input_image",
            "image_url": "https://example.com/" + "a" * 500,
        }
    ]
    clean = _sanitize_io(payload)
    assert "<omitted" in clean[0]["image_url"]


def test_prepare_langfuse_io_truncates():
    s = Settings(langfuse_log_io=True, langfuse_io_max_chars=256)
    out = prepare_langfuse_io({"text": "z" * 500}, settings=s)
    assert out is not None
    assert "truncated" in out["text"]
