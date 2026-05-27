from src.observability.langfuse_telemetry import _langfuse_trace_id


def test_langfuse_trace_id_uuid():
    uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert _langfuse_trace_id(uid) == "a1b2c3d4e5f67890abcdef1234567890"


def test_langfuse_trace_id_eval_session_is_hex32():
    sid = "eval74245b2e-q01_scope"
    trace_id = _langfuse_trace_id(sid)
    assert len(trace_id) == 32
    assert trace_id == trace_id.lower()
    int(trace_id, 16)
    assert _langfuse_trace_id(sid) == trace_id
