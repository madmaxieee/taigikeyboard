"""Fixtures for source-data semantics and mocked issue publication."""

import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from unittest.mock import Mock

import kautian_watch as watch
import pytest


def ods(path, sheets):
    document = ET.Element(watch.OFFICE + "document-content")
    for name, rows in sheets.items():
        table = ET.SubElement(document, watch.TABLE + "table", {watch.TABLE + "name": name})
        for values in rows:
            row = ET.SubElement(table, watch.TABLE + "table-row")
            for value in values:
                cell = ET.SubElement(row, watch.TABLE + "table-cell")
                if isinstance(value, int):
                    cell.set(watch.OFFICE + "value-type", "float")
                    cell.set(watch.OFFICE + "value", str(value))
                else:
                    ET.SubElement(cell, watch.TEXT + "p").text = value
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", ET.tostring(document))
    return path


def test_source_rows_counts_ids_and_modifications(tmp_path):
    columns = ["詞目id", "漢字", "羅馬字"]
    old = ods(
        tmp_path / "old.ods",
        {"詞目": [columns, [1, "重", "tîng"], [2, "重", "tāng"], [3, "古", "kóo"]]},
    )
    new = ods(
        tmp_path / "new.ods",
        {"詞目": [columns, [1, "重", "tîng"], [2, "重", "tāng-á"], [4, "早", "tsá"]]},
    )
    result = watch.compare(watch.read_ods(old), watch.read_ods(new))[0]
    assert (result.total_before, result.total_after) == (3, 3)
    assert result.added == [watch.RowChange(("4", "早", "tsá"), 1)]
    assert result.removed == [watch.RowChange(("3", "古", "kóo"), 1)]
    assert result.modified == [watch.Modification(("2", "重", "tāng"), ("2", "重", "tāng-á"))]


def test_duplicates_disable_pairing_across_complete_sheet():
    old = watch.Sheet(("詞目id", "漢字"), Counter({("1", "甲"): 2, ("2", "乙"): 1}))
    new = watch.Sheet(old.columns, Counter({("1", "甲"): 2, ("2", "丙"): 1}))
    result = watch.compare({"詞目": old}, {"詞目": new})[0]
    assert result.modified == []
    assert result.added == [watch.RowChange(("2", "丙"), 1)]
    result = watch.compare(
        {"姓": old}, {"姓": watch.Sheet(old.columns, Counter({("1", "甲"): 1}))}
    )[0]
    assert sum(row.count for row in result.removed) == 2


def test_order_and_packaging_do_not_change_semantics(tmp_path):
    old = watch.read_ods(
        ods(
            tmp_path / "old.ods",
            {"名": [["漢字", "羅馬字"], ["九", "kiú"], ["九", "káu"]]},
        )
    )
    new = watch.read_ods(
        ods(
            tmp_path / "new.ods",
            {"名": [["漢字", "羅馬字"], ["九", "káu"], ["九", "kiú"]]},
        )
    )
    assert watch.fingerprint(old) == watch.fingerprint(new)
    assert not any(watch.changed(sheet) for sheet in watch.compare(old, new))


def test_ods_whitespace_values_repetitions_and_blank_tails(tmp_path):
    row = ET.Element(watch.TABLE + "table-row")
    cell = ET.SubElement(row, watch.TABLE + "table-cell")
    paragraph = ET.SubElement(cell, watch.TEXT + "p")
    paragraph.text = "A"
    ET.SubElement(paragraph, watch.TEXT + "s", {watch.TEXT + "c": "2"}).tail = "B"
    ET.SubElement(paragraph, watch.TEXT + "tab").tail = "C"
    ET.SubElement(paragraph, watch.TEXT + "line-break").tail = "D"
    ET.SubElement(cell, watch.TEXT + "p").text = "E"
    ET.SubElement(
        row,
        watch.TABLE + "table-cell",
        {watch.TABLE + "number-columns-repeated": "16383"},
    )
    assert watch.row_values(row) == ("A  B\tC\nD\nE",)
    assert (
        watch.cell_value(
            ET.Element(
                "cell",
                {watch.OFFICE + "value-type": "float", watch.OFFICE + "value": "1.0"},
            )
        )
        == "1"
    )
    assert (
        watch.cell_value(
            ET.Element(
                "cell",
                {
                    watch.OFFICE + "value-type": "boolean",
                    watch.OFFICE + "boolean-value": "true",
                },
            )
        )
        == "true"
    )
    path = ods(tmp_path / "repeat.ods", {"名": [["漢字"], ["九"]]})
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    table = root.find(watch.TABLE + "table")
    table[1].set(watch.TABLE + "number-rows-repeated", "3")
    blank = ET.SubElement(
        table,
        watch.TABLE + "table-row",
        {watch.TABLE + "number-rows-repeated": "1048576"},
    )
    ET.SubElement(blank, watch.TABLE + "table-cell")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", ET.tostring(root))
    assert watch.read_ods(path)["名"].rows == Counter({("九",): 3})


def test_sheet_and_header_changes_are_explicit():
    old = {
        "keep": watch.Sheet(("a",), Counter()),
        "removed": watch.Sheet(("x",), Counter({("1",): 1})),
    }
    new = {
        "keep": watch.Sheet(("b",), Counter()),
        "added": watch.Sheet(("x",), Counter()),
    }
    result = watch.compare(old, new)
    assert all(watch.changed(sheet) for sheet in result)
    assert "@@ Column headers (null means sheet absent) @@" in watch.render(result, brief=True)


@pytest.mark.parametrize("content", [b"bad xml", b"<!DOCTYPE x><x/>", b"<x/>"])
def test_malformed_exports_fail(tmp_path, content):
    path = tmp_path / "bad.ods"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", content)
    with pytest.raises((ValueError, ET.ParseError)):
        watch.read_ods(path)


def test_reports_are_bounded_escaped_and_lossless():
    value = "@everyone <script> | [link](url) `code`" + "字" * 30000
    sheet = watch.SheetDiff(
        "名", ("漢字",), ("漢字",), 0, 50, [watch.RowChange((value,), 50)], [], []
    )
    summary = watch.render([sheet], brief=True)
    assert len(summary) < 24050
    assert "Summary truncated" in summary
    assert value not in summary
    assert "字" * 30000 in watch.render([sheet], brief=False)


def test_escape_entities_and_keep_modification_pairs_complete():
    assert watch.safe("@<>&'|#") == "&#64;&lt;&gt;&amp;&#x27;&#124;&#35;"
    sheet = watch.SheetDiff(
        "名",
        ("漢字",),
        ("漢字",),
        1,
        4,
        [watch.RowChange((str(i),), 1) for i in range(3)],
        [],
        [watch.Modification(("九",), ("八",))],
    )
    summary = watch.render([sheet], brief=True)
    assert "- 漢字: 九\n+ 漢字: 八" in summary
    sheet.modified = [watch.Modification(("字" * 1000,), ("語" * 1000,))] * 20
    summary = watch.render([sheet] * 30, brief=True)
    assert len(summary) < 24050
    assert summary.count("- 漢字:") == summary.count("+ 漢字:")
    assert summary.count("```diff") == len(re.findall(r"^```$", summary, re.MULTILINE))
    assert summary.count("<details>") == summary.count("</details>")


def test_approved_layout_shows_all_modifications_and_changed_fields_only():
    columns = ("詞目id", "漢字", "羅馬字")
    modifications = [
        watch.Modification((str(i), "水秤", "suí-tshìn"), (str(i), "水秤", "tsuí-tshìn"))
        for i in range(10)
    ]
    sheet = watch.SheetDiff("詞目", columns, columns, 29592, 29592, [], [], modifications)
    summary = watch.render([sheet], brief=True)
    assert "**0 added · 0 removed · 10 modified**" in summary
    assert "<summary>All 1 sheets</summary>" in summary
    assert "29,592" in summary
    assert summary.count("@@ 詞目id=") == 10
    assert "- 羅馬字: suí-tshìn\n+ 羅馬字: tsuí-tshìn" in summary
    assert "漢字: 水秤" not in summary
    assert "Before columns" not in summary
    assert "  漢字: 水秤" in watch.render([sheet], brief=False)


def test_duplicate_blank_and_overflow_column_values_keep_positions():
    columns = ("漢字", "漢字", "")
    sheet = watch.SheetDiff(
        "名", columns, columns, 0, 2, [watch.RowChange(("九", "八", "七", "六"), 2)], [], []
    )
    summary = watch.render([sheet], brief=True)
    for line in (
        "+ 漢字 [column 1]: 九",
        "+ 漢字 [column 2]: 八",
        "+ Column 3: 七",
        "+ Column 4: 六",
    ):
        assert line in summary
    assert "×2" in summary


def test_fenced_values_cannot_close_code_block_or_inject_unsigned_lines():
    value = "@everyone <script>\n````\n- forged\r\t"
    sheet = watch.SheetDiff(
        "名<script>|", ("漢字",), ("漢字",), 0, 1, [watch.RowChange((value,), 1)], [], []
    )
    summary = watch.render([sheet], brief=True)
    assert "`````diff\n" in summary
    assert "\n`````\n" in summary
    assert "+ 漢字: @everyone \\u003cscript>\\n````\\n- forged\\r\\t" in summary
    assert "\n- forged" not in summary
    assert "### 名&lt;script&gt;&#124;" in summary


def test_source_marker_text_cannot_break_generated_section():
    columns = (watch.START, watch.END)
    sheet = watch.SheetDiff(
        "名", None, columns, 0, 1, [watch.RowChange((watch.START, watch.END), 1)], [], []
    )
    for brief in (True, False):
        rendered = watch.render([sheet], brief=brief)
        assert watch.START not in rendered and watch.END not in rendered
        body = f"{watch.START}\n{rendered}\n{watch.END}"
        assert watch.generated_section(body) == body
        assert "\\u003c!-- kautian-watch:start -->" in rendered


def test_oversized_metadata_and_missing_name_are_bounded():
    sheet = watch.SheetDiff(
        "名",
        ("詞目id", "漢字"),
        ("詞目id", "漢字"),
        1,
        1,
        [],
        [],
        [watch.Modification(("1", "九"), ("1",))],
    )
    assert "+ 漢字: (empty)" in watch.render([sheet], brief=True)
    summary = watch.render([sheet] * 1000, brief=True)
    assert len(summary) <= 24000
    assert summary.count("<details>") == summary.count("</details>")
    assert "Summary truncated" in summary


def test_replace_only_generated_section_and_reject_bad_markers():
    section = f"{watch.START}\nnew\n{watch.END}"
    assert watch.replace_section("human", section) == "human\n\n" + section
    body = f"before\n{watch.START}\nold\n{watch.END}\nafter"
    assert watch.replace_section(body, section) == "before\n" + section + "\nafter"
    for body in (
        watch.START,
        watch.END,
        watch.END + watch.START,
        watch.START * 2 + watch.END,
    ):
        with pytest.raises(ValueError):
            watch.replace_section(body, section)


@pytest.fixture
def report(tmp_path, monkeypatch):
    before = ods(tmp_path / "old.ods", {"名": [["漢字"], ["九"]]})
    after = ods(tmp_path / "new.ods", {"名": [["漢字"], ["八"]]})
    output = tmp_path / "report"
    watch.generate(
        argparse.Namespace(
            committed=before, upstream=after, baseline_commit="abc123", output=output
        )
    )
    assert json.loads((output / "report.json").read_text())["sheets"][0]["added"][0]["values"] == [
        "八"
    ]
    return argparse.Namespace(
        repo="example/repo",
        report=output,
        artifact_url="https://example.org/artifact",
        run_url="https://example.org/run",
        last_modified="today",
    )


def issue(number=534, body="human refresh instructions", **extra):
    return {
        "number": number,
        "title": watch.TITLE,
        "user": {"login": "github-actions[bot]"},
        "body": body,
        **extra,
    }


def test_publish_create_existing_update_and_no_duplicate(report, monkeypatch):
    api = Mock(side_effect=[[[]], issue()])
    monkeypatch.setattr(watch, "github", api)
    watch.publish(report)
    assert api.call_args.kwargs["payload"]["title"] == watch.TITLE
    api.reset_mock(side_effect=True)
    # A title/author lookalike and a pull request must not be selected.
    lookalike = issue(1, user={"login": "human"})
    api.side_effect = [[[lookalike], [issue(), issue(2, pull_request={})]], issue(), {}]
    watch.publish(report)
    assert api.call_args.args[0].endswith("/534")
    body = api.call_args.kwargs["payload"]["body"]
    assert body.startswith("human refresh instructions\n")
    assert watch.FORMAT_MARKER in body
    assert "<summary>Comparison details</summary>" in body
    assert "--paginate" in api.call_args_list[0].args
    api.reset_mock(side_effect=True)
    api.side_effect = [[[issue(body=body)]], issue(body=body)]
    watch.publish(report)
    assert api.call_count == 2


def test_old_layout_or_markers_outside_generated_section_refresh_once(report, monkeypatch):
    identity = (report.report / "fingerprint.txt").read_text()
    marker = f"<!-- kautian-watch:data:{identity} -->"
    for body in (
        f"{watch.START}\n{marker}\nold layout\n{watch.END}",
        f"{marker}\n{watch.FORMAT_MARKER}\nHuman text",
    ):
        api = Mock(side_effect=[[[issue(body=body)]], issue(body=body), {}])
        monkeypatch.setattr(watch, "github", api)
        watch.publish(report)
        assert api.call_count == 3
        updated = api.call_args.kwargs["payload"]["body"]
        assert watch.FORMAT_MARKER in watch.generated_section(updated)


def test_no_change_does_not_open_issue_and_clears_stale_report(report, monkeypatch):
    data_path = report.report / "report.json"
    data = json.loads(data_path.read_text())
    data["upstream_data_sha256"] = data["baseline_data_sha256"]
    data_path.write_text(json.dumps(data))
    (report.report / "fingerprint.txt").write_text("new identity")
    (report.report / "summary.md").write_text("No data differences from the committed capture.")
    api = Mock(return_value=[[]])
    monkeypatch.setattr(watch, "github", api)
    watch.publish(report)
    assert api.call_count == 1
    api.reset_mock()
    api.side_effect = [[[issue()]], issue(), {}]
    watch.publish(report)
    assert "No data differences" in api.call_args.kwargs["payload"]["body"]


def test_github_errors_propagate_without_mutation(report, monkeypatch):
    api = Mock(side_effect=RuntimeError("API failed"))
    monkeypatch.setattr(watch, "github", api)
    with pytest.raises(RuntimeError, match="API failed"):
        watch.publish(report)
    assert api.call_count == 1
