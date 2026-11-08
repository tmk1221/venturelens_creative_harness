from post_core.workers import contract


def test_emit_and_parse_roundtrip(capsys):
    contract.emit("step", label="ingest")
    out = capsys.readouterr().out.strip()
    assert out.startswith("##POST ")
    ev = contract.parse_line(out)
    assert ev == {"kind": "step", "label": "ingest"}


def test_parse_line_rejects_non_contract_lines():
    assert contract.parse_line("plain narration") is None
    assert contract.parse_line("##POST not json") is None
    assert contract.parse_line("##POST [1, 2, 3]") is None  # not an object
    assert contract.parse_line("##POST {\"no\": \"kind\"}") is None


def test_parse_line_passes_through_extra_fields():
    line = contract.format_line("result", ok=False, detail="rate limited", retry_at="2026-09-22T00:00:00Z")
    ev = contract.parse_line(line)
    assert ev["retry_at"] == "2026-09-22T00:00:00Z"


def test_exit_codes_are_distinct():
    codes = {contract.EXIT_OK, contract.EXIT_FAILED, contract.EXIT_USAGE,
             contract.EXIT_RETRY_LATER, contract.EXIT_NEEDS_HUMAN}
    assert codes == {0, 1, 2, 3, 4}


def test_post_emit_sh_defines_a_post_emit_function():
    assert "post_emit()" in contract.POST_EMIT_SH
    assert contract.POST_EMIT_SH_PATH.is_file()
    assert contract.POST_EMIT_SH == contract.POST_EMIT_SH_PATH.read_text()
