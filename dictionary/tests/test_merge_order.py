"""Source precedence must survive unrelated dictionary additions."""

import pandas as pd
import pytest

from build import merge_csv
from common.source_bits import MAIN_SOURCE_COLUMNS


@pytest.mark.parametrize("unrelated_count", [0, 1, 11, 16, 17, 100])
def test_merge_preserves_source_and_row_precedence(tmp_path, monkeypatch, unrelated_count):
    inputs = [("kautian.csv", "kautian"), ("taigitv.csv", "taigitv"), ("itaigi.csv", "itaigi")]

    def write_source(path, source, entries):
        rows = [
            {
                "hanzi": hanzi,
                "tl": tl,
                "poj": poj,
                "frequency": frequency,
                **{column: column == source for column in MAIN_SOURCE_COLUMNS},
            }
            for hanzi, tl, poj, frequency in entries
        ]
        pd.DataFrame(rows).to_csv(tmp_path / path, index=False)

    # trace: both official spellings normalize to sàu-thôo-kha; the first
    # Kautian row supplies TL/POJ, while frequency and source flags aggregate.
    write_source("kautian.csv", "kautian", [
        ("掃塗跤", "sàu thôo-kha", "sàu thô͘-kha", 16),
        ("掃塗跤", "sàu-thôo-kha", "sàu-thô͘-kha", 16),
        ("重", "tîng", "têng", 1),
        ("重", "tāng", "tāng", 1),
        *[(f"probe-{index}", "a", "a", 0) for index in range(unrelated_count)],
    ])
    write_source("taigitv.csv", "taigitv", [("掃塗跤", "sàu-thôo-kha", "sàu-thô͘-kha", 20)])
    # The unofficial row occurs before the official rows after concatenation
    # below, so this also exercises the official-priority partition.
    write_source("itaigi.csv", "itaigi", [("掃塗跤", "sàu-thôo-kha", "sàu-thô͘-kha", 30)])
    monkeypatch.setattr(merge_csv, "BASE_DIR", tmp_path)
    monkeypatch.setattr(merge_csv, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(merge_csv, "INPUT_FILES", [inputs[2], *inputs[:2]])
    for loader in ("_load_khiin_new_entries", "_load_dev_supplement", "_load_lkk_entries"):
        monkeypatch.setattr(merge_csv, loader, lambda *args: None)

    merge_csv.main()

    result = pd.read_csv(tmp_path / "output/dictionary.csv")
    selected = result[result.hanzi == "掃塗跤"]
    assert len(selected) == 1
    row = selected.iloc[0]
    assert (row.tl, row.poj) == ("sàu thôo-kha", "sàu thô͘-kha")
    assert row.frequency == 30
    assert row.kautian and row.taigitv and row.itaigi
    assert set(result.loc[result.hanzi == "重", "tl"]) == {"tîng", "tāng"}
