# WMT26 synthetic references

This release contains one complete synthetic reference for every document with
retained official WMT26 General MT cESA evidence: **3,781 documents**,
**12,669 source segments**, and **23 directions**.

## Selection procedure

1. Apply the published GenMT annotation processing: authoritative RESET
   handling, exclusion of tutorial and attention-check items, and the
   low-reliability-annotator filter.
2. Exclude 550 score records for translations not present in the corresponding screen's displayed target set. These cannot be valid cESA observations for the translation in question.
3. A translation can be assessed in several screens. For each
   `(source segment, system)`, first average its retained cESA scores and
   major-error-span counts across those assessments. For each displayed
   `(document, system)` candidate, then average the per-segment cESA values
   over its source segments. All selected document candidates had complete
   segment coverage.
4. Select the document candidate with the highest average cESA score. Exact
   ties prefer fewer average major-error spans, then more annotations, then
   lexical system name.
5. Keep its full document translation by default. A segment is considered for
   repair only when the document-selected translation has per-segment average
   cESA strictly below 80 or an average major-error count above zero. Among
   the candidates actually displayed and assessed for that same segment,
   select the highest average cESA candidate. An exact cESA tie prefers fewer
   average major-error spans; remaining ties prefer more annotations and then
   system name. Replace the document segment only for a higher average cESA
   score, or an equal score with fewer average major-error spans; otherwise
   retain it.

## Descriptive results

The repair condition was met on 1,589 segments; 862
segments (6.80%) were replaced by a better
locally observed translation. On the same evidence used for selection, the
mean cESA score increases from 91.88 for the
document-only selection to 93.34 after repair,
and the mean major-error count decreases from 0.137
to 0.092. These are in-sample descriptive
figures, not held-out estimates of synthetic-reference quality.

`wmt26_synthetic_references.jsonl` contains the complete synthetic documents;
`segment_provenance.csv` records every document and segment decision; and
`direction_summary.csv` gives per-direction statistics.

## System-level cESA score

The synthetic reference can be treated as one composite system. A translation
may have been assessed in several screens, so its segment score is first the
arithmetic mean of all retained human cESA scores for that item and system.
The direction-level score is then the arithmetic mean over the selected
per-segment scores. This is exactly the item-then-system averaging used in
`humeval/02b-analyze_results.py`.

| Direction | System-level cESA |
| --- | ---: |
| Czech → German | 95.30 |
| Czech → Ukrainian | 94.32 |
| Czech → Vietnamese | 98.16 |
| English → Egyptian Arabic | 87.61 |
| English → Belarusian | 93.03 |
| English → Czech | 90.23 |
| English → German | 92.52 |
| English → Estonian | 92.65 |
| English → Armenian | 96.43 |
| English → Indonesian | 96.41 |
| English → Icelandic | 96.50 |
| English → Japanese | 98.47 |
| English → Kazakh | 94.39 |
| English → Korean | 91.49 |
| English → Ligurian | 91.14 |
| English → Ladin | 86.26 |
| English → Russian | 96.41 |
| English → Northern Sámi | 75.98 |
| English → Thai | 94.81 |
| English → Ukrainian | 97.34 |
| English → Simplified Chinese | 90.48 |
| English → Traditional Chinese | 92.55 |
| Simplified Chinese → Japanese | 89.98 |
