"""Fixtures for source-data semantics and mocked issue publication."""

import argparse
import json
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
    assert "Sheet added/removed or column headers changed" in watch.render(result, brief=True)


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
    assert "@everyone" not in summary and "<script>" not in summary
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
    assert "modified before" in summary and "modified after" in summary
    sheet.modified = [watch.Modification(("字" * 1000,), ("語" * 1000,))] * 20
    summary = watch.render([sheet] * 30, brief=True)
    assert len(summary) < 24050
    assert summary.count("modified before") == summary.count("modified after")


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
    assert "--paginate" in api.call_args_list[0].args
    api.reset_mock(side_effect=True)
    api.side_effect = [[[issue(body=body)]], issue(body=body)]
    watch.publish(report)
    assert api.call_count == 2


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
