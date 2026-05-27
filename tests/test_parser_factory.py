import pytest

from src.pdf.parsers.factory import ParserFactoryError, normalize_parser_backend


def test_normalize_mineru():
    assert normalize_parser_backend("mineru") == "mineru"
    assert normalize_parser_backend("MINERU") == "mineru"


@pytest.mark.parametrize("backend", ["fusion", "docling", "scheme_b", "dual"])
def test_removed_backends_raise(backend: str):
    with pytest.raises(ParserFactoryError, match="已移除"):
        normalize_parser_backend(backend)
