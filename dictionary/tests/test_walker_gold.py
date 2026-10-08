"""tools/walker_gold.py — input variants, excerpt windows and the offline walker simulator.

Run from `dictionary/`:
    PYTHONPATH=. python3 -m pytest tests/test_walker_gold.py -q
"""

from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from tools.walker_gold import Item, Resolved, Row, Simulator, windows


def row(hanzi: str, tl: str, tl_num: str, frequency: int, tl_notone: str, syllable_count: int) -> Row:
    return Row(hanzi, tl, frequency, tl_num, tl_notone, tl_num, tl_notone, "", "", syllable_count, True)


KAU_SIU = row("教授", "kàu-siū", "kau3siu7", 10, "kausiu", 2)
KAU = row("到", "kàu", "kau3", 17_333, "kau", 1)
SIU = row("受", "siū", "siu7", 8_975, "siu", 1)


class InputVariantTests(unittest.TestCase):
    def test_inputs_cover_every_variant_from_the_dictionary_keys(self) -> None:
        resolved = Resolved(Item("dev-0000", "dev", "phrase", "dict:"), [KAU_SIU, KAU])
        inputs = resolved.inputs()
        self.assertEqual(inputs["tl_full"], "kau3siu7kau3")
        # Digit on each word's first syllable only.
        self.assertEqual(inputs["tl_partial"], "kau3siukau3")
        self.assertEqual(inputs["tl_toneless"], "kausiukau")
        self.assertEqual(inputs["tl_hyphen"], "kau3-siu7-kau3")


class WindowTests(unittest.TestCase):
    def test_windows_stop_at_breaks_and_respect_the_syllable_range(self) -> None:
        words = [KAU, KAU_SIU, None, KAU]
        # A lone one-syllable word is below MIN_SYLLABLES; nothing crosses the break.
        self.assertEqual(windows(words), [(0, 2), (1, 2)])


class SimulatorTests(unittest.TestCase):
    def simulator(self, counts: dict[str, int]) -> Simulator:
        by_tl_num = defaultdict(list)
        for r in (KAU_SIU, KAU, SIU):
            by_tl_num[r.tl_num].append(r)
        dictionary = SimpleNamespace(
            by_tl_num=by_tl_num,
            count=lambda r: counts.get(r.hanzi, 0),
            tokens=3_627_713,
            vocabulary=167_907,
        )
        return Simulator(dictionary, picks={})

    def test_current_model_composes_the_single_characters(self) -> None:
        # trace: current cost 到 5.3177 + 受 5.8460 = 11.1636 < 教授 11.2279
        path = self.simulator({}).best_path(["kau3", "siu7"], "current", 0.0)
        self.assertEqual([r.hanzi for r in path], ["到", "受"])

    def test_a2_model_keeps_the_word_on_corpus_counts(self) -> None:
        # trace: a2@0.5, denominator 3,627,713 + 0.5 × 167,907; cost = −ln p / len^0.2 × syll^0.2
        # 教授 −ln(246.5/D) / 6^0.2 × 2^0.2 = 7.72; 到 4.24 + 受 5.22 = 9.46 > 7.72
        simulator = self.simulator({"教授": 246, "到": 18_902, "受": 5_574})
        path = simulator.best_path(["kau3", "siu7"], "a2", 0.5)
        self.assertEqual([r.hanzi for r in path], ["教授"])


if __name__ == "__main__":
    unittest.main()
