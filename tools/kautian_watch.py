#!/usr/bin/env python3
"""Compare MoE ODS data and maintain the generated section of its update issue."""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TITLE = "chore(dictionary): MoE kautian.ods has new data"
START, END = "<!-- kautian-watch:start -->", "<!-- kautian-watch:end -->"
FORMAT_MARKER = "<!-- kautian-watch:format:2 -->"
# These are source-record identifiers, not dictionary word/deduplication keys.
SOURCE_KEYS = {
    "詞目": ("詞目id",),
    "義項": ("詞目id", "義項id"),
    "例句": ("詞目id", "義項id", "例句順序"),
}
Row = tuple[str, ...]


@dataclass
class Sheet:
    columns: Row
    rows: Counter[Row]


@dataclass
class RowChange:
    values: Row
    count: int


@dataclass
class Modification:
    before: Row
    after: Row


@dataclass
class SheetDiff:
    name: str
    columns_before: Row | None
    columns_after: Row | None
    total_before: int
    total_after: int
    added: list[RowChange]
    removed: list[RowChange]
    modified: list[Modification]


def repeat(element: ET.Element, attribute: str, maximum: int) -> int:
    count = int(element.get(attribute, "1"))
    if not 1 <= count <= maximum:
        raise ValueError(f"Invalid ODS repetition: {attribute}={count}")
    return count


def text_content(element: ET.Element) -> str:
    special = {TEXT + "tab": "\t", TEXT + "line-break": "\n"}
    if element.tag == TEXT + "s":
        return " " * repeat(element, TEXT + "c", 32767)
    if element.tag in special:
        return special[element.tag]
    return (element.text or "") + "".join(
        text_content(child) + (child.tail or "") for child in element
    )


def cell_value(cell: ET.Element) -> str:
    if cell.get(TABLE + "formula"):
        raise ValueError("Unexpected formula in source export")
    kind = cell.get(OFFICE + "value-type", "string")
    if kind in {"float", "currency", "percentage"}:
        return format(Decimal(cell.attrib[OFFICE + "value"]).normalize(), "f")
    for attribute in ("boolean-value", "date-value", "time-value", "string-value"):
        if OFFICE + attribute in cell.attrib:
            return cell.attrib[OFFICE + attribute]
    if kind not in {"string", "void"}:
        raise ValueError(f"Unsupported ODS cell type: {kind}")
    return "\n".join(text_content(p) for p in cell.findall(TEXT + "p"))


def row_values(element: ET.Element) -> Row:
    values: list[str] = []
    pending_empty = 0
    for cell in element:
        if cell.tag not in {TABLE + "table-cell", TABLE + "covered-table-cell"}:
            continue
        count = repeat(cell, TABLE + "number-columns-repeated", 16384)
        value = cell_value(cell)
        if not value:
            pending_empty += count
            continue
        if len(values) + pending_empty + count > 256:
            raise ValueError("Source export exceeds 256 populated columns")
        values.extend([""] * pending_empty + [value] * count)
        pending_empty = 0
    return tuple(values)


def read_ods(path: Path) -> dict[str, Sheet]:
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo("content.xml").file_size > 128 * 1024 * 1024:
            raise ValueError("ODS content.xml exceeds 128 MiB")
        content = archive.read("content.xml")
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise ValueError("Source export must not contain XML entity declarations")
    sheets: dict[str, Sheet] = {}
    current: Sheet | None = None
    for event, element in ET.iterparse(io.BytesIO(content), events=("start", "end")):
        if element.tag == TABLE + "table":
            if event == "start":
                name = element.attrib[TABLE + "name"]
                if current is not None or name in sheets:
                    raise ValueError("Nested or duplicate ODS table")
                current = Sheet((), Counter())
                sheets[name] = current
            else:
                if current is None or not current.columns:
                    raise ValueError("Source sheet has no column headers")
                current = None
                element.clear()
        elif event == "end" and element.tag == TABLE + "table-row":
            if current is None:
                raise ValueError("ODS row outside a sheet")
            values = row_values(element)
            count = repeat(element, TABLE + "number-rows-repeated", 1048576)
            if values:
                if not current.columns:
                    current.columns = values
                    count -= 1
                if count:
                    current.rows[values] += count
            element.clear()
    if not sheets:
        raise ValueError("Source export contains no sheets")
    return sheets


def fingerprint(sheets: dict[str, Sheet]) -> str:
    data = [
        (name, sheet.columns, sorted(sheet.rows.items())) for name, sheet in sorted(sheets.items())
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def unique_rows(sheet: Sheet, columns: tuple[str, ...]) -> dict[Row, Row]:
    if not all(column in sheet.columns for column in columns):
        return {}
    indices = [sheet.columns.index(column) for column in columns]
    indexed: dict[Row, Row] = {}
    for row, count in sheet.rows.items():
        key = tuple(row[index] if index < len(row) else "" for index in indices)
        if count != 1 or not all(key) or key in indexed:
            return {}
        indexed[key] = row
    return indexed


def compare(before: dict[str, Sheet], after: dict[str, Sheet]) -> list[SheetDiff]:
    differences = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        old_rows = old.rows if old else Counter()
        new_rows = new.rows if new else Counter()
        removed, added = old_rows - new_rows, new_rows - old_rows
        modified = []
        if old and new and old.columns == new.columns and name in SOURCE_KEYS:
            old_index = unique_rows(old, SOURCE_KEYS[name])
            new_index = unique_rows(new, SOURCE_KEYS[name])
            for key in sorted(old_index.keys() & new_index.keys()):
                left, right = old_index[key], new_index[key]
                if removed[left] and added[right]:
                    modified.append(Modification(left, right))
                    removed[left] -= 1
                    added[right] -= 1
        differences.append(
            SheetDiff(
                name,
                old.columns if old else None,
                new.columns if new else None,
                sum(old_rows.values()),
                sum(new_rows.values()),
                [RowChange(row, count) for row, count in sorted(added.items()) if count],
                [RowChange(row, count) for row, count in sorted(removed.items()) if count],
                modified,
            )
        )
    return differences


def changed(sheet: SheetDiff) -> bool:
    return bool(
        sheet.added
        or sheet.removed
        or sheet.modified
        or sheet.columns_before != sheet.columns_after
    )


def safe(value: str, limit: int | None = None) -> str:
    if limit is not None and len(value) > limit:
        value = value[:limit] + "…"
    # Escape Markdown/HTML and mentions before embedding upstream text in issues.
    replacements = {c: f"&#{ord(c)};" for c in "\\`*_{}[]()#+-.!|~@\t"}
    replacements["\n"] = "<br>"
    return "".join(replacements.get(char, html.escape(char)) for char in value)


def counts(sheet: SheetDiff) -> tuple[int, int, int]:
    return (
        sum(row.count for row in sheet.added),
        sum(row.count for row in sheet.removed),
        len(sheet.modified),
    )


def summary_table(sheets: list[SheetDiff], *, brief: bool) -> str:
    lines = [
        "| Sheet | Before | After | Added | Removed | Modified |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sheet in sheets:
        totals = (sheet.total_before, sheet.total_after, *counts(sheet))
        lines.append(
            f"| {safe(sheet.name, 80 if brief else None)} | "
            + " | ".join(f"{number:,}" for number in totals)
            + " |"
        )
    return "\n".join(lines)


def code_text(value: str) -> str:
    # Fenced code preserves Unicode; JSON escaping keeps controls on one signed line.
    # Marker-like source text must not confuse the generated-section parser.
    return json.dumps(value, ensure_ascii=False)[1:-1].replace("<", "\\u003c")


def column_label(columns: Row, index: int) -> str:
    if index >= len(columns) or not columns[index]:
        return f"Column {index + 1}"
    name = columns[index]
    return name if columns.count(name) == 1 else f"{name} [column {index + 1}]"


def row_context(columns: Row, row: Row) -> str:
    fields = dict(zip(columns, row))
    identifiers = [
        f"{column}={value}" for column, value in zip(columns, row) if column.endswith("id")
    ]
    name = fields.get("漢字", fields.get("詞目漢字", fields.get("羅馬字", "")))
    if target := fields.get("對應詞目漢字"):
        name += f" → {target}"
    return code_text(" · ".join([*identifiers, name] if name else identifiers))


def diff_hunks(sheet: SheetDiff, *, brief: bool):
    if not brief or sheet.columns_before != sheet.columns_after:
        yield "\n".join(
            [
                "@@ Column headers (null means sheet absent) @@",
                "- " + json.dumps(sheet.columns_before, ensure_ascii=False).replace("<", "\\u003c"),
                "+ " + json.dumps(sheet.columns_after, ensure_ascii=False).replace("<", "\\u003c"),
            ]
        )
    for modification in sheet.modified:
        columns = sheet.columns_before or ()
        context = row_context(columns, modification.before)
        name_index = columns.index("漢字") if "漢字" in columns else None
        if name_index is not None:
            old_name = (
                modification.before[name_index] if name_index < len(modification.before) else ""
            )
            new_name = (
                modification.after[name_index] if name_index < len(modification.after) else ""
            )
            if old_name != new_name:
                context += " → " + code_text(new_name)
        lines = [f"@@ {context} @@"]
        for index in range(max(len(modification.before), len(modification.after))):
            before = modification.before[index] if index < len(modification.before) else None
            after = modification.after[index] if index < len(modification.after) else None
            label = code_text(column_label(columns, index))
            if before != after:
                for sign, value in (("-", before), ("+", after)):
                    display = code_text(value) if value else "(empty)"
                    lines.append(f"{sign} {label}: {display}")
            elif not brief:
                lines.append(f"  {label}: {code_text(before) if before else '(empty)'}")
        yield "\n".join(lines)
    for sign, rows, columns in (
        ("+", sheet.added, sheet.columns_after),
        ("-", sheet.removed, sheet.columns_before),
    ):
        for row in rows:
            columns = columns or ()
            context = row_context(columns, row.values)
            suffix = f" · ×{row.count}" if row.count > 1 else ""
            lines = [f"@@ {context}{suffix} @@"]
            for index, value in enumerate(row.values):
                lines.append(
                    f"{sign} {code_text(column_label(columns, index))}: "
                    + (code_text(value) or "(empty)")
                )
            yield "\n".join(lines)


def render(differences: list[SheetDiff], *, brief: bool) -> str:
    active = [sheet for sheet in differences if changed(sheet)]
    totals = [sum(counts(sheet)[index] for sheet in active) for index in range(3)]
    blocks = [
        "## Data diff",
        (
            f"**{totals[0]} added · {totals[1]} removed · {totals[2]} modified** "
            f"across {len(active)} sheets."
        ),
        "Counts refer to source rows; modified rows are counted separately.",
    ]
    if not active:
        blocks.append("No data differences from the committed capture.")
    tables = [summary_table(active, brief=brief)] if active else []
    tables.append(
        f"<details>\n<summary>All {len(differences)} sheets</summary>\n\n"
        + summary_table(differences, brief=brief)
        + "\n\n</details>"
    )
    omitted = "Summary truncated; see full report for remaining changes."
    limit = 24000 if brief else None
    for table in tables:
        if limit and len("\n\n".join([*blocks, table, omitted])) > limit:
            return "\n\n".join([*blocks, omitted]) + "\n"
        blocks.append(table)
    for sheet in active:
        labels = ", ".join(
            f"{number} {label}"
            for number, label in zip(counts(sheet), ("added", "removed", "modified"))
            if number
        )
        title = f"### {safe(sheet.name, 80 if brief else None)} — " + (
            labels or "column headers changed"
        )
        hunks, fence_length, body_length = [], 3, 0
        truncated = False
        remaining = limit - len("\n\n".join([*blocks, title, omitted])) - 24 if limit else None
        for hunk in diff_hunks(sheet, brief=brief):
            candidate_fence = max(
                fence_length, max((len(m[0]) + 1 for m in re.finditer(r"`+", hunk)), default=3)
            )
            candidate_length = body_length + len(hunk) + 2
            if remaining is not None and candidate_length + 2 * candidate_fence > remaining:
                truncated = True
                break
            hunks.append(hunk)
            body_length, fence_length = candidate_length, candidate_fence
        if hunks:
            fence = "`" * fence_length
            blocks.append(title + f"\n\n{fence}diff\n" + "\n\n".join(hunks) + f"\n{fence}")
        if truncated:
            blocks.append(omitted)
            break
    return "\n\n".join(blocks) + "\n"


def generate(arguments: argparse.Namespace) -> None:
    before, after = read_ods(arguments.committed), read_ods(arguments.upstream)
    differences = compare(before, after)
    data = {
        "baseline_commit": arguments.baseline_commit,
        "baseline_data_sha256": fingerprint(before),
        "upstream_data_sha256": fingerprint(after),
        "upstream_file_sha256": hashlib.sha256(arguments.upstream.read_bytes()).hexdigest(),
        "sheets": [asdict(sheet) for sheet in differences],
    }
    identity = hashlib.sha256(
        (data["baseline_data_sha256"] + data["upstream_data_sha256"]).encode()
    ).hexdigest()
    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "fingerprint.txt").write_text(identity, encoding="utf-8")
    (arguments.output / "report.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for filename, brief in (("summary.md", True), ("diff.md", False)):
        (arguments.output / filename).write_text(
            ("" if brief else f"Baseline commit: `{arguments.baseline_commit}`\n\n")
            + render(differences, brief=brief),
            encoding="utf-8",
        )


def generated_section(body: str) -> str | None:
    if START not in body and END not in body:
        return None
    if body.count(START) != 1 or body.count(END) != 1 or body.index(START) > body.index(END):
        raise ValueError("Issue has malformed generated-section markers; preserve it unchanged")
    return body[body.index(START) : body.index(END) + len(END)]


def replace_section(body: str, section: str) -> str:
    old = generated_section(body)
    result = body.replace(old, section, 1) if old is not None else body.rstrip() + "\n\n" + section
    if len(result) > 60000:
        raise ValueError("Issue body too large; preserve human text unchanged")
    return result


def github(*arguments: str, payload: dict[str, str] | None = None):
    command = ["gh", "api", *arguments]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def publish(arguments: argparse.Namespace) -> None:
    endpoint = f"repos/{arguments.repo}/issues"
    pages = github(
        f"{endpoint}?state=open&creator=github-actions%5Bbot%5D&per_page=100",
        "--paginate",
        "--slurp",
    )
    matches = [
        issue
        for page in pages
        for issue in page
        if issue["title"] == TITLE
        and issue["user"]["login"] == "github-actions[bot]"
        and "pull_request" not in issue
    ]
    if len(matches) > 1:
        raise ValueError("Multiple matching watch issues; refusing ambiguous update")
    identity = (arguments.report / "fingerprint.txt").read_text(encoding="utf-8")
    marker = f"<!-- kautian-watch:data:{identity} -->"
    current = github(f"{endpoint}/{matches[0]['number']}") if matches else None
    existing = generated_section(current["body"] or "") if current else None
    if existing and marker in existing and FORMAT_MARKER in existing:
        print("Issue already has this data diff")
        return
    report = json.loads((arguments.report / "report.json").read_text(encoding="utf-8"))
    if not current and report["baseline_data_sha256"] == report["upstream_data_sha256"]:
        print("No data changes; no issue needed")
        return
    summary = (arguments.report / "summary.md").read_text(encoding="utf-8")
    section = (
        f"{START}\n{marker}\n{FORMAT_MARKER}\n{summary}\n"
        f"[Full report (Markdown + JSON)]({arguments.artifact_url}) · [Detection run]({arguments.run_url})\n\n"
        "<details>\n<summary>Comparison details</summary>\n\n"
        f"- Baseline commit: `{report['baseline_commit']}`\n"
        f"- Upstream Last-Modified: {safe(arguments.last_modified, 200)}\n"
        f"- Upstream file SHA-256: `{report['upstream_file_sha256']}`\n"
        "- Full report retained for 90 days; GitHub sign-in required.\n"
        "- Modified rows pair unique source IDs in both complete sheets. "
        "Other changes appear as additions/removals.\n\n</details>\n"
        f"{END}"
    )
    if current:
        github(
            f"{endpoint}/{current['number']}",
            "--method",
            "PATCH",
            payload={"body": replace_section(current["body"] or "", section)},
        )
        print(f"Updated issue #{current['number']}")
    else:
        body = (
            "MoE published data differing from the committed capture.\n\n"
            "Source: https://sutian.moe.edu.tw/media/senn/ods/kautian.ods\n\n"
            "Refresh: replace `dictionary/sources/official/kautian/data/raw/kautian.ods`, "
            "then `make dict` (regenerate `word_unigrams.tsv` / `word_bigrams.tsv` "
            "with `build.corpus_bigrams` if a unigram row is no longer a dictionary record) "
            "and commit rebuilt artifacts."
        )
        issue = github(
            endpoint,
            "--method",
            "POST",
            payload={"title": TITLE, "body": replace_section(body, section)},
        )
        print(f"Created issue #{issue['number']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    comparison = commands.add_parser("compare")
    comparison.add_argument("committed", type=Path)
    comparison.add_argument("upstream", type=Path)
    comparison.add_argument("--baseline-commit", required=True)
    comparison.add_argument("--output", type=Path, required=True)
    publication = commands.add_parser("publish")
    publication.add_argument("--repo", required=True)
    publication.add_argument("--report", type=Path, required=True)
    publication.add_argument("--artifact-url", required=True)
    publication.add_argument("--run-url", required=True)
    publication.add_argument("--last-modified", default="unknown")
    arguments = parser.parse_args()
    (generate if arguments.command == "compare" else publish)(arguments)


if __name__ == "__main__":
    main()
