# E1 — Unified Word Frequency for the Walker

> **Type**: Planning (multi-PR roadmap)
> **Keywords**: `walker`, `edge_cost`, `word_unigrams`, `segmentation`, `slot 0`, `gold set`
> **Status**: Planned — direction approved by the maintainer 2026-10-08 ("proceed with your recommendation"); pre-impl review in progress
> **Last updated**: 2026-10-08

Release scope and timing are the maintainer's call; nothing here is assigned to a release.

---

## 1. Problem (grounded in code)

Fully toned TL `kau3siu7` puts the walker composition 到受 at slot 0; the dictionary word 教授 *kàu-siū* sits lower. Reproduced with `engine/composing/tests/candidate_dump.rs` against the production artifacts with no user data → every platform. Found in the 2026-10-08 desktop upgrade sim; root cause co-confirmed by Codex.

**Mechanism.**

- Walker edge cost (`engine/composing/src/lattice/cost.rs:320-372`, khiin port): `ln(CORPUS_TOTAL_FREQ / (1 + freq)) / toneless_len^0.2 × syllable_count^0.2 − ln(1 + δ)`; the walker takes the min-sum path (`lattice/walker.rs:181`).
- `freq` = `DictionaryRecord.frequency`, attached by the pipeline stage `dictionary/common/stages/frequency.py:20-27` through `dictionary/common/frequency.py:22-100`, which mixes three scales:
  1. single characters — `char_freq_merged.txt`, counting every occurrence of the character, **including inside other words** (到 *kàu* 18,902; 受 *siū* 8,975);
  2. multi-syllable words — `khiin_frequency.csv` word counts (教授 *kàu-siū* 10);
  3. everything else — `get_default_frequency` = `50 // syllables` (25 for 75,057 two-syllable rows, 16 for 39,992 three-syllable rows).
- Edge `frequency` = `EdgeBest::span_frequency`, the max over the key's homophones (`engine/lexicon/src/continuous/mod.rs:1085-1121`; `engine/composing/src/continuous.rs:843-866`).
- Numbers: 到 5.3177 + 受 5.8460 = 11.1636 < 教授 11.2279.
- Slot 0 is the walker path (`continuous.rs:1310-1446`); the §22 promotion fires only when the walker's hanji already equals a full-span dictionary word, so it cannot rescue 教授.
- Control: `tai5gi2` → 台語 (freq 394, cost 8.66) — a word whose khiin count happens to be large enough.

**Same-corpus recompute** (`dictionary/shared/data/word_unigrams.tsv`, N = 3,629,550 tokens): 教授 246, 到/*kàu* 18,902, 受/*siū* 5,574 → 教授 7.70 vs 到+受 9.42 — 教授 wins.

**Exposure** (previous session, a risk screen, not an error count): in fully toned 2–3 syllable input, 1,368 dictionary words lose slot 0 to a different hanji composition; 812 of them occur in the corpus. Many losers are odd variants (ê話 → 的話), where the composition is the better answer.

## 2. Facts measured for this plan (2026-10-08, `main` `a45bb704`)

| Fact | Value | Source |
|---|---|---|
| `word_unigrams.tsv` rows / tokens | 52,017 / 3,629,550 | file; `count` = sum of 9 source columns |
| Rows that are dictionary words | 52,017 / 52,017 | join on `(hanzi, tl)` with `output/dictionary.csv` (`corpus_bigrams.py` whitelists dictionary words) |
| Dictionary rows with a corpus count | 52,017 / 168,958 (31 %) | 1-syll 7,980/25,562 · 2-syll 34,922/87,771 · 3-syll 7,736/43,085 · 4-syll 1,379/12,540 |
| Per-source tokens | bible_nt 407,675 · nmtl 997,565 · kipsupin 939,274 · khinhoan 762,511 · icorpus 403,074 · moe_kautian 例句 105,640 · kok4hau7 6,652 · sinpak 5,322 · taigi_typing 1,837 | column sums |
| Full-tone keys (`tl_num`) where the old-frequency argmax homophone ≠ the corpus argmax | 5,110 of 15,267 multi-homophone keys (2,401 with corpus best ≥ 10) | e.g. `kap` 洽 (old 4,927 / corpus 0) vs 佮 (2,668 / 22,637); `koh` 擱 vs 閣; `beh` 卜 vs 欲; `tsit` 今 vs 這; `in-uī` 因爲 vs 因為 |
| `dictionary.bin` readers | Rust only (`engine/lexicon::dictionary_reader`); iOS bundles the `assets/dictionaries` folder reference; Linux installs the four files by name (`linux/Makefile:164`) | grep |

The last-but-one row decides §4 D3.

## 3. Direction — A2 (walker probability from one segmented corpus)

1. **Build time**: one walker probability per dictionary row `(hanzi, canonical TL)` (Core Principle #6) from `word_unigrams.tsv`, with the `taigi_typing` column excluded (it is the held-out gold source, §5).
2. **Unseen rows** take the **same model's** smoothed value (Lidstone add-α over the dictionary vocabulary: `p = (c + α) / (N + α·V)`) — no fallback to the old frequencies (AGENTS.md § No redundant fallback).
3. **Denominator** = the corpus total (`N + α·V`), computed at build time; `CORPUS_TOTAL_FREQ` and its regeneration guard retire.
4. **Candidate-list sort is untouched**: `DictionaryRecord.frequency` keeps feeding `ranking::calculate_continuous_score`, the FST row order, `association.bin` v1 pairs and every non-walker consumer. The walker reads a separate field.
5. No bigram (bigram P6/P7 stay closed).

### Not adopted

| Option | Why not |
|---|---|
| A1 — fixed multiplier on multi-syllable frequency | Keeps two scales; the factor is arbitrary and breaks as the sources change. |
| B — no sentence when the whole buffer is a word (librime `references/librime/src/rime/gear/script_translator.cc:495-506`) | Promotes every odd full-span variant (ê話) over a better composition; drops the walker exactly where the exposure screen says it helps. |
| C — fixed per-word penalty (librime `references/librime/src/rime/gear/grammar.h:23-26`, `kPenalty = ln 1e-6` per entry) | A per-edge constant tunes segmentation granularity, not the scale mismatch; 教授 vs 到受 stays decided by mixed counts. |
| Per-source weighting of the corpus | YAGNI until the dev split shows a domain skew (bible_nt is 11 % of tokens); revisit only with numbers (P4). |
| Katz / Good-Turing back-off to a character model | More machinery than the decision needs; Lidstone is the khiin / McBopomofo level of modelling. Revisit only if the dev split shows unseen-word pricing as the dominant error class. |

## 4. Design forks (Codex + maintainer)

**D1 — where the walker value lives.** Recommend **`dictionary.bin` v4**: add `walker_cost: u16` (milli-nats of `−ln p`, smoothing already applied at build time) after `kautian_subtag`. One reader, one artifact, no packaging change on any platform (`linux/Makefile:164` lists files by name; a new file would touch every packager). +2 B × 168,958 ≈ 330 KB. `u16` covers `−ln p` ≤ 65.5 nats; the worst case at α = 0.1 is ≈ 17.5. Alternative: a sidecar `walker_lm.bin` (rowid-parallel array) — rejected for the packaging fan-out.

**D2 — the cost formula.** `edge_cost` takes the record's `walker_cost` in place of `ln(N / (1 + freq))`; the khiin length terms (`÷ toneless_len^0.2 × syllable_count^0.2`) and the OOV per-char `BIG` (`OOV_PER_CHAR_PENALTY`) stay as they are in P3. The custom-entry proxy and the learned / user-selected floor move from the frequency domain to the cost domain as named constants: `CUSTOM_EDGE_COST` and the selection floor `CUSTOM_EDGE_COST − ln(min(1, δ / BOOST_ALPHA))` (algebraically the current `ln(N / (1 + 2000·s))`, re-anchored to the new distribution in P3).

**D3 — which homophone prices the edge.** The brief proposes "price the edge on the picked word's own value instead of the homophone max". Measured (§2): with the candidate sort unchanged, the pick follows the *old* frequency, and on 5,110 full-tone keys the pick is a homophone the corpus rarely or never writes. Pricing on the pick would price `kap` as 洽 (corpus 0 → unseen) instead of 佮 (22,637), and the same for `koh`, `beh`, `tsit`, `in`, … — the commonest function words would start losing their segmentation. Options:

| | Edge cost | Edge word (slot-0 hanji) | Effect |
|---|---|---|---|
| **(c) recommended for P3** | min `walker_cost` over the key's homophones (today's "is this span a word" decoupling, `continuous-input-ranking.md` §3.2 / #69, re-expressed in the new scale) | unchanged pick (`pick_edge_word`, `CandidateSortKey` order) | Fixes segmentation only; slot-0 orthography unchanged |
| (a) the brief as written | the pick's own `walker_cost` | unchanged pick | Regresses function words (above) |
| (b) | the pick's own `walker_cost` | walker edges pick by (user weight, then corpus probability) | Fixes segmentation **and** moves slot-0 hanji toward the corpus orthography (擱→閣, 卜→欲, 今→這, 因爲→因為) on thousands of keys; slot 0 and the span-local list order can disagree. A product decision, so its own phase (P5), maintainer-gated |

**D4 — tie to the user signal.** Unchanged: user weight stays the leading pick dimension; single-syllable edges keep `WALKER_SINGLE_SYLLABLE_USER_DELTA_SCALE` (re-checked in P4, not assumed).

## 5. Gold set and measurement (before any A2 code)

**Items.** One row per item in `engine/composing/tests/data/walker_gold.tsv`:

```
id  split  category  canonical_tl  accepted  source
```

- `canonical_tl` carries the gold word boundaries (space between words, `-` / `--` inside one).
- `accepted` = `|`-separated hanji answers, each with the same boundaries; the corpus line's own hanji is the first accepted answer automatically, orthographic alternatives (閣/擱, 佮/甲) are added by human judgement.
- `category` ∈ `common` (corpus count ≥ 100) · `rare` (1–99) · `unseen` (dictionary word with no corpus count) · `variant` (key with competing orthographies) · `phrase` (2–4 dictionary words, ≤ 8 syllables).
- `source` = `kautian:<dic_url>` or `typing:<article>:<line>`.

**Splits.**

| Split | Source | Use |
|---|---|---|
| `dev` (~250 items) | 教典 example sentences (`corpus/taigi-typing/exampleSentences.js`) + hand-picked word items (rare / unseen / variant), incl. the fixed regression inputs below | Tuning α, `CUSTOM_EDGE_COST`, the user-delta scale. Its sentences overlap `moe_kautian` 例句 in the training counts — dev numbers are optimistic by construction |
| `heldout` (~150 items) | `mapped` articles of `corpus/taigi-typing/articles.js` | Never used for tuning. The `taigi_typing` column (1,837 tokens) is excluded from the walker counts, so these items are unseen by the model. Read once per phase, aggregates only |

**Licensing** (`corpus/README.md`): articles may only be quoted as short excerpts and never copied; 教典 sentences are CC BY-ND (quote, never rework). Gold items are therefore excerpts of ≤ 8 syllables with a source pointer — never a whole sentence or article.

**Input variants generated by the harness** from `canonical_tl` (no hand-typed inputs): TL full tone (digits) · TL partial tone (digit on each word's first syllable only) · TL toneless · POJ full tone · POJ toneless · TPS (`phonetics::api::tl_numeric_to_tps`). Up to 6 inputs per item.

**Metrics** (per split × category × input variant):

1. **Slot-0 acceptable rate** — slot 0's hanji ∈ `accepted`.
2. **Boundary accuracy** — F1 of slot 0's word boundaries vs. the gold boundaries.
3. **Top-k displacement** — rank of the first accepted answer in the full list (not found = k+1), reported as mean and as the count that moved by ≥ 3 between two runs.

**Harness**: `engine/composing/tests/walker_gold.rs`, `#[ignore]`d like `candidate_dump.rs`, driving the production artifacts through the real `Start → FetchAtPos` path; prints a table and writes a JSON summary. `GOLD_SPLIT=heldout` prints aggregates only.

**Fixed regression inputs** (asserted from P3 on, in the `prod` test target): `kau3siu7` → 教授 · `tai5gi2` → 台語 · `hoogua` (§22 promotion) · `taiuan` → 台灣 · `ginalangtsiahpngbesai` → 囡仔人食飯袂使.

## 6. Phases

| Phase | Content | Size (hand-written) | Behaviour change | Status |
|---|---|---|---|---|
| **P0** | Admin: this roadmap under `docs/architecture/`, `docs/roadmap.md` Active entry, memory topic file | docs | none | Pending |
| **P1** | Gold set (dev + heldout) + `walker_gold.rs` harness + baseline report `docs/reports/<date>-e1-walker-baseline.md` on current `main` | ~350 LOC + TSV | none | Pending |
| **P2** | Build: `dictionary/build/walker_lm.py` (counts − `taigi_typing`, Lidstone α, `−ln p` → milli-nats), `dictionary.bin` v4 writer + verifier, `output/walker_lm_stats.txt` (N, V, α, unseen cost, percentiles); engine v4 reader + `RawCandidate.walker_cost`; walker still prices on `frequency` | ~400 | none — S0 golden diff empty | Pending |
| **P3** | Switch: `edge_cost` on `walker_cost` (D2); `EdgeBest` carries min `walker_cost` (D3 (c)); `CUSTOM_EDGE_COST` + selection floor + learned-phrase floor (`continuous.rs:822-848`) in the cost domain, re-anchored with the rule used for 2,000 (a custom entry beats a top single-character split, not a top single character); retire `CORPUS_TOTAL_FREQ` + `corpus_total_freq.txt`; fixed regression tests; S0 golden diff reviewed line by line; docs (`continuous-input-ranking.md`, `binary-format.md`, `cost.rs` head) | ~450 | **yes** — slot 0 / segmentation | Pending |
| **P4** | Calibration on dev only: α ∈ {0.1, 0.5, 1}, `CUSTOM_EDGE_COST`, `WALKER_SINGLE_SYLLABLE_USER_DELTA_SCALE` (0.0 kept unless dev shows otherwise); length exponents re-checked, changed only with a dev win; one held-out read; report | ~150 + report | constants only | Pending |
| P5 (maintainer-gated) | D3 (b): walker edge pick by corpus probability → slot-0 orthography change | ~250 | **yes** — slot-0 hanji | Not opened |

Every phase from P2 on: `make dict` → `make build`, refreshed artifacts committed; post-PR gate per touched platform via `tools/test_select.py`; dogfood items on one mobile and one desktop platform for P3 / P4.

## 7. Best-practices alignment

| Mainstream practice | Source `file:line` | This plan |
|---|---|---|
| One corpus probability for every segmentable unit, single characters included: `p = corpus_count / total_count` over one table | `references/khiin-rs/khiin/src/db/init/csv.rs:57,81`; consumed by `khiin/src/data/segmenter.rs:70-93` | P2 / P3 — our port kept khiin's formula but fed it two scales |
| Character counts made standalone by subtracting in-phrase occurrences; unseen phrase priced at a fixed pseudo-count of the same normaliser | `references/McBopomofo/Source/Data/curation/builders/frequency_builder.py:50-66` | P2 — segmented-corpus counts are standalone by construction; Lidstone is the same-model unseen price |
| Walker = Viterbi / relaxation over `Σ −ln p` | `references/McBopomofo/Source/Engine/gramambular2/reading_grid.cpp:134`; `cost.rs` head | unchanged |
| User phrases enter the same weight space as dictionary entries | `references/librime/src/rime/dict/user_dictionary.cc` (`formula_d`) | P3 — custom / learned floors move into the cost domain instead of a frequency proxy |

Rules: `~/.claude/rules/planning.md` (roadmap + memory, grounded, P0 admin) · `diagnosis-discipline.md` § Verify pipeline claims (§2 measurements; D3 premise check) · `code-review-rules.md` §8 (Codex pre-impl per phase) · `docs/contributing/known-pitfalls.md` § Trace before assert (P3 expected values traced from `walker_lm_stats.txt`, not from output).

## 8. Decisions

The maintainer, 2026-10-08, after the plain-language summary (goal: "slot 0 should be the word the user types often and wants"): "proceed with your recommendation". Recorded as:

1. **D3** — (c) for P3. (b) stays an unopened, maintainer-gated P5; slot-0 orthography is not changed by this plan.
2. **Gold judgement** — the corpus line's hanji is the automatic first answer; Claude drafts the alternative orthographies, the maintainer reviews only the `variant` and `phrase` rows.
3. **Corpus weighting** — raw sum of the 8 non-held-out sources; revisited only if dev shows a domain skew (P4).
