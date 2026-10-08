# -*- coding: utf-8 -*-
"""Shared constants + helpers for dictionary build scripts.

Each build script needs the same BASE_DIR / OUTPUT_DIR / logger / build
id, so centralise here. Scripts import from this module instead of
rebuilding the boilerplate prelude.
"""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
MERGED_CSV = OUTPUT_DIR / "dictionary.csv"
SHARED_DATA_DIR = BASE_DIR / "shared" / "data"
# Segmented corpus word counts (`build.corpus_bigrams`); the walker model's input.
UNIGRAMS_TSV = SHARED_DATA_DIR / "word_unigrams.tsv"
# Walker model smoothing α (`build.walker_lm`); here because `build_id` hashes it.
# Provisional 10 (P1 exposure: 68 dictionary words broken vs 1,059 at α 0.5, while
# `calib` phrases score the same at 0.5–10); P4 calibrates it on the calib split.
WALKER_ALPHA = 10.0

# Build scripts live under dictionary/build/; importing common.* requires
# dictionary/ on sys.path. Each build script calls this once at import time.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def build_id() -> int:
    """The u32 written into the `build_ts` header slot of both binaries.

    CRC-32 of the merged `output/dictionary.csv` — the input both
    `dictionary.bin` and `association.bin` are built from — chained over the
    walker model's inputs (`word_unigrams.tsv` and α, which only
    `dictionary.bin` reads). So the same inputs always produce byte-identical
    binaries, a model change changes the id, and the two binaries of one
    build always carry the same value. It was `time.time()`, which made every
    rebuild differ from the committed artifact even when nothing else had
    changed. The engine stores the slot but never reads it.
    """
    checksum = zlib.crc32(MERGED_CSV.read_bytes())
    checksum = zlib.crc32(UNIGRAMS_TSV.read_bytes(), checksum)
    return zlib.crc32(f"alpha={WALKER_ALPHA!r}".encode(), checksum)
