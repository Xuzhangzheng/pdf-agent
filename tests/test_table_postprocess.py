from src.pdf.table_postprocess import normalize_table_latex


def test_multicolumn_extracts_aql_values():
    raw = r"| 键宽 | \multicolumn{3}{c}{1.0} | 1.0 | \multicolumn{3}{c}{1.5} |"
    out = normalize_table_latex(raw)
    assert "\\multicolumn" not in out
    assert "1.0" in out
    assert "1.5" in out


def test_multicolumn_with_tab_in_alignment():
    raw = r"\multicolumn{3}{c	}{2.5}"
    out = normalize_table_latex(raw)
    assert out.strip() == "2.5"


def test_user_sample_row_fragments():
    line = r"键宽 b \multicolumn{3}{c	}{1.0} 1.0 \multicolumn{3}{c	}{1.5}"
    out = normalize_table_latex(line)
    assert "1.0" in out
    assert "1.5" in out
    assert "multicolumn" not in out.lower()
