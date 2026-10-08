# E1 Walker Baseline (P1)

> **Type**: Report (dated snapshot — frozen)
> **Keywords**: `walker`, `gold set`, `baseline`, `slot 0`, `word_unigrams`
> **Date**: 2026-10-08 · `main` `411804d1` + P1 tooling · production artifacts of 2026-10-07 (`assets/dictionaries/`)
> **Plan**: [`architecture/unified-word-frequency-roadmap.md`](../architecture/unified-word-frequency-roadmap.md) §5–§6 (P1)

Slot-0 quality of the walker as it ships today, measured on the E1 gold set, plus the offline simulation of the A2 cost that P2–P4 build. No engine behaviour changed in P1.

## Summary

- Fully toned TL, `dev`: slot 0 is the gold text **81.1 %** of the time and the gold words (orthography aside) **92.1 %**. Toneless input drops to **60.4 % / 63.8 %**. TPS full tone is **74.0 % / 81.1 %**, below TL full tone on the same items.
- `calib` (typing articles, held out from the counts), TL full tone: **80.9 % / 89.7 %**.
- **Two kinds of miss.**
  - Segmentation, which E1 targets: 教授 → 到受, 鹿仔 → 樂 仔, 桃仔 → 迌 仔, 序大 → 是 大.
  - Which character a one-syllable edge shows: 賣 → 袂, 由 → 油, 角 → 覺, 隻 → 才, 个 → 的. These are the edge pick (plan D3 (b), P5), which P3 leaves alone. They are a large share of the remaining `phrase` misses.
- **Runtime D3 screen** (the engine's own pick for each of 14,849 multi-homophone keys). With default sources, the pick is not the corpus's most-written word on **2,016** keys. On **236** of them the pick never occurs in the corpus while the winner occurs ≥ 10 times (傳導 vs 傳道 1,611; 二億 vs 利益 1,135). Pricing an edge on its pick (option (a)) would price those keys as unseen; this confirms (c).
- **Simulated A2** (TL full tone), current → α 0.5 / 10:
  - `dev` exact 81 → 86 / 86 %; segmented 88 → 91 / 93 %.
  - `calib` exact 81 → 85 / 85 %; segmented 88 → 96 / 96 %.
  - The regression 教授 is fixed at every α.
- **α must be searched far wider than the plan's {0.1, 0.5, 1}.** At α = 0.5, A2 breaks 1,077 dictionary words that win their own key today (雨鞋 → 予 鞋, 織女 → 這 你) while fixing 1,167. At α = 10 it breaks 69 and fixes 1,320.
- **About 224 k corpus words are synthetic.** They were OOV words split by the old frequency, and they produce ≥ 448 k of the 3.39 M counted tokens (≥ 13 %; ≥ 45 % in `icorpus_hanji`).
- **The committed `word_unigrams.tsv` is stale.** It predates later dictionary rebuilds: `taigi_bible_nt` is 407,675 tokens in the file but 334,126 when counted today.

## 1. Reproduce

```sh
cd dictionary
PYTHONPATH=. python3 -m tools.walker_gold select     # only to rebuild the gold file (needs corpus/taigi-corpus)
PYTHONPATH=. python3 -m tools.walker_gold resolve    # → engine/target/walker_gold/{resolved,edge_keys}.tsv
cd ..
GOLD_OUT=/tmp/baseline.tsv GOLD_SLOT0_OUT=/tmp/slot0.tsv \
  cargo test --manifest-path engine/Cargo.toml -p composing --test prod walker_ -- --include-ignored --nocapture
cd dictionary
PYTHONPATH=. python3 -m tools.walker_gold d3
PYTHONPATH=. python3 -m tools.walker_gold simulate --engine-slot0 /tmp/slot0.tsv
PYTHONPATH=. python3 -m tools.walker_gold exposure --alpha 0.5
```

Engine runs use the default install's sources (built in the harness from named toggles through `lexicon::api::dictionary_filter_bitmask`; variant and khiin rows off), no user data, no context, and the literal-roman lead off. The `all` D3 row uses every source.

## 2. Gold set

`engine/composing/tests/data/walker_gold.tsv` (seed `20261008`) holds 415 items. It stores pointers and judgements only; the corpus text is read from the `corpus/taigi-typing` submodule at resolve time. Every gold word is a dictionary word a default install can show.

| Split | Items | Source | Categories |
|---|---|---|---|
| `dev` | 265 | 教典 example sentences (one excerpt per sentence) + dictionary items | phrase 120 · common 15 · rare 35 · neutral 15 · variant 35 · unseen 40 · regression 5 |
| `calib` | 68 | typing articles 10, 31, 32, 33, 35 (≤ 2 excerpts per line) | phrase 58 · common 5 · rare 5 |
| `final` | 82 | typing articles 1, 21, 22, 23, 34 | not read |

- 3 of the 88 typing lines also occur in another corpus source and are excluded.
- `extra_accepted` is empty in this baseline: `exact` means the corpus's own orthography. `segmented` means the same word boundaries, with each word a homophone of the gold word under its fully toned key. That is the orthography-blind measure E1 targets.
- Word boundaries come from slot 0's **displayed** roman, one word per space-separated run, which is what the user sees. The §22 promotion shows one dictionary word where the walker took several edges with the same hanji and reading, and that counts as one word. `tl_hyphen` shows the user's typed separators, so it has no boundary columns.
- `final` was not run through the engine. While the tool was being brought up, the simulator printed `final`'s aggregate row once, before the `--splits` guard existed. Nothing was tuned on it.

## 3. Engine baseline

Column definitions:

- `exact`: slot 0 is the gold text.
- `segmented`: slot 0 has the gold boundaries and homophones.
- `top5`: an acceptable whole-buffer answer is within the first five candidates.
- `mean rank`: 0-based, capped at 5, where 5 means not in the first five.

| Split | Variant | n | exact % | segmented % | boundary F1 | top5 % | mean rank |
|---|---|---|---|---|---|---|---|
| dev | tl_full | 265 | 81.1 | 92.1 | 0.949 | 90.6 | 0.57 |
| dev | tl_partial | 265 | 78.1 | 88.3 | 0.927 | 89.8 | 0.64 |
| dev | tl_toneless | 265 | 60.4 | 63.8 | 0.868 | 76.6 | 1.37 |
| dev | tl_hyphen | 265 | 81.9 | – | – | 90.6 | 0.56 |
| dev | poj_full | 265 | 81.1 | 92.1 | 0.949 | 90.6 | 0.57 |
| dev | poj_toneless | 265 | 60.8 | 64.5 | 0.880 | 76.2 | 1.38 |
| dev | tps_full | 265 | 74.0 | 81.1 | 0.915 | 85.7 | 0.85 |
| dev | tps_toneless | 265 | 61.9 | 65.7 | 0.884 | 78.1 | 1.30 |
| calib | tl_full | 68 | 80.9 | 89.7 | 0.962 | 82.4 | 0.90 |
| calib | tl_partial | 68 | 80.9 | 89.7 | 0.962 | 82.4 | 0.90 |
| calib | tl_toneless | 68 | 57.4 | 58.8 | 0.943 | 58.8 | 2.07 |
| calib | tl_hyphen | 68 | 80.9 | – | – | 82.4 | 0.90 |
| calib | poj_full | 68 | 80.9 | 89.7 | 0.962 | 82.4 | 0.90 |
| calib | poj_toneless | 68 | 55.9 | 58.8 | 0.958 | 57.4 | 2.15 |
| calib | tps_full | 68 | 73.5 | 77.9 | 0.956 | 75.0 | 1.26 |
| calib | tps_toneless | 68 | 58.8 | 60.3 | 0.951 | 60.3 | 2.00 |

By category (all variants):

| Split | Category | n | exact % | segmented % | top5 % |
|---|---|---|---|---|---|
| dev | phrase | 960 | 64.1 | 69.6 | 67.1 |
| dev | common | 120 | 96.7 | 96.2 | 100.0 |
| dev | rare | 280 | 87.1 | 86.1 | 100.0 |
| dev | unseen | 320 | 94.1 | 93.6 | 98.4 |
| dev | variant | 280 | 50.0 | 80.4 | 100.0 |
| dev | neutral | 120 | 72.5 | 70.5 | 98.3 |
| dev | regression | 40 | 80.0 | 60.0 | 100.0 |
| calib | phrase | 464 | 67.9 | 72.4 | 67.9 |
| calib | common | 40 | 100.0 | 100.0 | 100.0 |
| calib | rare | 40 | 80.0 | 80.0 | 100.0 |

Reading the TL full-tone misses (`GOLD_FAILURES=1`, `dev` / `calib`):

- **Segmentation** (E1): 教授 → 到受, 鹿仔 → 樂 仔, 桃仔 → 迌 仔, 鴨仔 → 矣 仔, 序大 → 是 大, 毋但 → 毋 若.
- **One-syllable edge pick** (D3 (b) / P5, unchanged by P3): 賣 → 袂, 由 → 油, 仙 → 先, 都 → 多, 齣 → 出, 地 → 帝, 角 → 覺, 隻 → 才, and the orthography pairs 个 → 的, 誠 → 成, 甲 → 佮.
- **Multi-syllable variant pick**: 祭品 → 製品, 解酒 → 改酒, 又閣 → 又koh, 相借問 → sio借問.
- TPS full tone trails TL full tone on the same items (74.0 % vs 81.1 % exact). This is outside E1's root cause and is noted for a separate look.

## 4. Runtime D3 screen

`walker_edge_picks` types each of the 14,849 fully toned keys that have more than one hanji, and records the first whole-key candidate that is one of the key's words. `tools.walker_gold d3` compares that pick with the corpus's most-written hanji for the key, using counts without `taigi_typing`.

| Sources | Keys | Pick ≠ corpus winner | Pick unseen, winner ≥ 10 | Top examples (pick (count) → winner (count)) |
|---|---|---|---|---|
| default | 14,849 | 2,016 | 236 | 傳導 (0) → 傳道 (1,611) · 二億 (0) → 利益 (1,135) · tsiânn做 (0) → 成做 (658) · 保戶 (0) → 保護 (467) · 凌勒 (0) → 能力 (355) |
| all | 14,849 | 3,993 | 752 | 今 (0) → 這 (20,489) · 因爲 (0) → 因為 (11,646) · 得着 (0) → 得著 (3,734) · 省乜 (0) → 甚物 (2,880) |

Under option (a), every row in the last column would be priced as an unseen word. D3 (c), the min over homophones, keeps their span priced by the winner.

## 5. Simulated A2 (offline)

`tools.walker_gold simulate` runs the walker over the fully toned syllables, under these rules:

- Edges are dictionary words visible under the default sources.
- The khiin length terms are priced on the picked word's own `syllable_count` and toneless key length.
- Each edge's word is the engine's own pick from §4.
- The model is either the current cost or A2: `−ln((c + α) / (N + α·V))`, min over homophones, `taigi_typing` excluded, N = 3,627,713, V = 167,907.

| Stratum | n | current exact / seg | α 0.5 | α 2 | α 10 | α 50 |
|---|---|---|---|---|---|---|
| dev / all | 265 | 81 % / 88 % | 86 / 91 | 85 / 91 | 86 / 93 | 87 / 94 |
| dev / phrase | 120 | 78 / 88 | 82 / 89 | 82 / 88 | 82 / 89 | 83 / 88 |
| dev / neutral | 15 | 73 / 40 | 100 / 80 | 100 / 80 | 100 / 80 | 100 / 100 |
| dev / rare | 35 | 94 / 91 | 97 / 94 | 97 / 94 | 100 / 100 | 100 / 100 |
| dev / unseen | 40 | 98 / 98 | 95 / 92 | 95 / 95 | 98 / 98 | 98 / 98 |
| dev / variant | 35 | 57 / 97 | 60 / 100 | 60 / 100 | 60 / 100 | 60 / 100 |
| dev / regression | 5 | 80 / 40 | 100 / 60 | 100 / 60 | 100 / 60 | 100 / 60 |
| calib / all | 68 | 81 / 88 | 85 / 96 | 85 / 96 | 85 / 96 | 85 / 97 |
| calib / phrase | 58 | 79 / 90 | 83 / 95 | 83 / 95 | 83 / 95 | 83 / 97 |

**Simulator fidelity.** On 320 / 333 `dev` + `calib` items, the simulator and the engine agree on slot 0's hanji **and** its displayed word lengths under the current model. In the 13 that differ, the hanji are the same and only the word lengths differ: the engine shows 毋 知 where the simulator joins 毋知, and the simulator shows 做 人 where the engine shows 做人.

At α = 0.5, 38 items change slot 0:

- **Better** (30): 教授, 朗讀, 開工, 官員, 蟮螂, 車頭, 鹿仔 ×2, 桃仔 ×2, 鴨仔, 姪仔, 孫仔, 頭仔, 囡仔 ×2, 豆仔, 有夠, 本來, 毋但, 著愛, 閣較, 起床, 才 會當, 鼻目喙 生做 (boundaries; 誠 still shows 成), and 一个 / 兩个 / 這个 ×5 (one word where the gold has two, same text).
- **Same hanji, worse boundaries** (5): 才閣 → 才 閣, 攏 是 → 攏是 ×2, 時到 → 時 到, 來回 → 來 回.
- **Worse hanji** (2): 敢是 → 感 是, 猶是 → 野 是.
- **Still wrong** (1): 咬 人 (共人 → 共 人).

### Exposure

`tools.walker_gold exposure` covers all 39,482 fully toned 2–3 syllable keys that have a default-visible word. A key "loses" when slot 0 is not one of the key's own words as one edge.

| Model | Keys where the word loses | of which the word has a corpus count | word → split | split → word |
|---|---|---|---|---|
| current | 1,485 | 1,300 | – | – |
| A2 α 0.5 | 1,395 | 538 | 1,077 | 1,167 |
| A2 α 2 | 723 | 392 | 451 | 1,213 |
| A2 α 10 | 234 | 142 | 69 | 1,320 |
| A2 α 50 | 25 | 16 | 1 | 1,461 |

This table supersedes the previous session's screen (1,368 / 812), which used another pick rule. "Word wins its key" is not ground truth: 共人 → 共 人 is a correct split. So α is chosen on `calib` phrases, not on this table, because a large α also inflates unseen multi-syllable words inside sentences.

## 6. Corpus counts

Re-counting today's corpus against today's dictionary (read-only run of `corpus_bigrams.count_source`):

| Source | in-vocabulary tokens | OOV words subsegmented | OOV dropped |
|---|---|---|---|
| icorpus_hanji | 403,074 | 91,565 | 1,212 |
| kipsupin_2009 | 910,716 | 47,867 | 35,251 |
| nmtl_dadwt | 884,237 | 39,464 | 13,925 |
| khinhoan_pojbh | 743,267 | 29,557 | 11,777 |
| taigi_bible_nt | 334,126 | 13,388 | 3,824 |
| moe_kautian | 105,640 | 1,790 | 4,639 |
| kok4hau7 | 6,652 | 313 | 240 |
| sinpak_900leku | 5,322 | 41 | 306 |
| taigi_typing | 1,837 | 61 | 103 |

- The 224,046 subsegmented OOV words (`taigi_typing` excluded) each add ≥ 2 in-vocabulary tokens. Their pieces are chosen by "fewest pieces, then highest summed **old** frequency" (`dictionary/build/corpus_bigrams.py:273-290`). That makes ≥ 448,092 of the 3,393,034 counted tokens (≥ 13.2 %) synthetic splits steered by the scale E1 replaces; for `icorpus_hanji` it is ≥ 45.4 %.
- Three sources' in-vocabulary totals differ from the committed `word_unigrams.tsv` columns:
  - `taigi_bible_nt`: 407,675 in the file → 334,126 counted today;
  - `kipsupin_2009`: 939,274 → 910,716;
  - `nmtl_dadwt`: 997,565 → 884,237.

## 7. Consequences for P2–P4

1. **P2.**
   - Regenerate `word_unigrams.tsv` against the current dictionary, or record why the 2026-09-28 file stays. `association.bin` v2 reads the sibling `word_bigrams.tsv`, so a regeneration is its own reviewed diff.
   - Decide whether the subsegment tie-break keeps the old frequency (a known residue) or counts an OOV word's pieces fractionally.
2. **P3.** Keep the five fixed regression inputs. Add 鹿仔 / 桃仔 as prod assertions only if P4 keeps them fixed.
3. **P4.**
   - Search α over {0.5, 2, 10, 50}, not {0.1, 0.5, 1}, on `calib` phrases, reading the `word → split` exposure alongside.
   - If no single α serves both unseen words and phrases, the next candidate is a length-aware unseen prior (khiin `segmenter.rs:82-86`, McBopomofo `frequency_builder.py:55`).
4. **Outside E1.**
   - One-syllable edge picks and orthography (賣/袂, 角/覺, 个/的) are the P5 decision.
   - The TPS gap gets its own look.
5. **Not measured in P1, moved to P3 acceptance:**
   - key-by-key (incremental) input;
   - typed spaces;
   - POJ spelling aliases;
   - a `reading` category (one hanji, several readings);
   - unseen-by-cause strata.
