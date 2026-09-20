#!/usr/bin/env python3
"""Build WMT26 synthetic references from retained cESA annotations.

The procedure is deliberately transparent and deterministic:

1. Apply the same RESET, non-content-item, and low-reliability-annotator
   filtering as ``02a-filter_data.py``.
2. For every (direction, source segment, system), average all retained cESA
   scores across all screens in which that translation was assessed. The
   corresponding average counts of minor and major spans are kept as
   provenance and for deterministic tie-breaking.
3. Select one candidate translation for each document by its mean cESA score
   over the document's annotated segments.  Ties prefer fewer major errors,
   then more annotated segments, then a lexical system-name order.
4. Preserve that document translation except where the selected candidate has
   a per-segment averaged cESA below 80 or a non-zero average number of major
   errors across its retained assessments.
   Such a segment is replaced only when another displayed, human-assessed
   candidate has a higher per-segment average cESA score, or the same average
   cESA score and fewer average major-error spans.

The output is suitable for segment-level evaluation while retaining a
document-level translation wherever the human evidence does not flag a clear
local concern.  It is not an independent estimate of reference quality: the
same human evidence is used for selection and for the descriptive statistics
reported by this script.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sacrebleu import CHRF as SacrebleuCHRF


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ANNOTATIONS = REPO_ROOT.parent.parent / "latest_genmt_human_eval" / "annotations.json"
DEFAULT_DATA = REPO_ROOT / "data"
DEFAULT_OUTPUT = REPO_ROOT / "synthetic_references"

SCORE_FLOOR = 80.0
HUMAN_MODEL_TO_REFERENCE_KEY = {
    "Human (from scratch)": "refA",
    "Human (postediting)": "refPE",
}
LANGUAGE_NAMES = {
    "arz_Arab": "Egyptian Arabic",
    "bel_Cyrl": "Belarusian",
    "ces_Latn": "Czech",
    "deu_Latn": "German",
    "ekk_Latn": "Estonian",
    "eng_Latn": "English",
    "hye_Armn": "Armenian",
    "ind_Latn": "Indonesian",
    "isl_Latn": "Icelandic",
    "jpn_Jpan": "Japanese",
    "kaz_Cyrl": "Kazakh",
    "kor_Hang": "Korean",
    "lij_Latn": "Ligurian",
    "lld_Latn": "Ladin",
    "rus_Cyrl": "Russian",
    "sme_Latn": "Northern Sámi",
    "tha_Thai": "Thai",
    "ukr_Cyrl": "Ukrainian",
    "vie_Latn": "Vietnamese",
    "zho_Hans": "Simplified Chinese",
    "zho_Hant_TW": "Traditional Chinese",
}
CHRF_PARAGRAPH_THRESHOLD = 85.0
SPLIT_LENGTH_RATIO = 1.3
CHRF = SacrebleuCHRF()


def _finite_score(value: object) -> float | None:
    """Return one finite cESA score, or ``None`` for a missing/invalid value."""
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    score = float(value)
    if not 0.0 <= score <= 100.0:
        raise ValueError(f"cESA score outside [0, 100]: {score}")
    return score


def _is_content_line(line: dict[str, Any]) -> bool:
    """Match the content-item exclusions in 02a-filter_data.py."""
    items = line.get("item")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return False
    item_id = items[0].get("item_id")
    if not isinstance(item_id, str):
        return False
    return not item_id.startswith("attention_check_") and "_#_tutorial_#_" not in item_id


def apply_resets_and_remove_noncontent(
    raw: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Apply authoritative dump-order RESET semantics used by GenMT."""
    retained: dict[str, list[dict[str, Any]]] = {}
    for direction, lines in raw.items():
        by_user: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for line in lines:
            user = line.get("user_id")
            if not isinstance(user, str):
                continue
            if line.get("annotation") == "__RESET__":
                by_user[user] = []
            elif _is_content_line(line):
                by_user[user].append(line)
        retained[direction] = [line for user_lines in by_user.values() for line in user_lines]
    return retained


def _line_observations(line: dict[str, Any]) -> Iterable[tuple[str, float]]:
    """Yield (system, score) observations with valid cESA scores."""
    annotations = line.get("annotation")
    if not isinstance(annotations, list):
        return
    for item_annotation in annotations:
        if not isinstance(item_annotation, dict):
            continue
        for system, annotation in item_annotation.items():
            if not isinstance(system, str) or not isinstance(annotation, dict):
                continue
            score = _finite_score(annotation.get("score"))
            if score is not None:
                yield system, score


def low_reliability_users(lines: list[dict[str, Any]]) -> set[str]:
    """Reproduce GenMT's published low-reliability-user rule exactly.

    ``02a-filter_data.py`` estimates pairwise score expectations from all
    retained content lines, then flags a user if their mean compatibility is
    below 0.75.  The all-lines pool is intentional here: this mirrors the
    pipeline that produced the published GenMT human results.
    """
    by_user: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for line in lines:
        user = line.get("user_id")
        if isinstance(user, str):
            by_user[user].append(line)

    all_scores: dict[str, list[float]] = collections.defaultdict(list)
    for line in lines:
        for system, score in _line_observations(line):
            all_scores[system].append(score)

    means = {system: statistics.mean(scores) for system, scores in all_scores.items()}
    variances = {
        system: statistics.variance(scores)
        for system, scores in all_scores.items()
        if len(scores) > 1
    }
    pair_mean = {
        (first, second): means[first] - means[second]
        for first in means
        for second in means
        if first != second and len(all_scores[first]) > 10 and len(all_scores[second]) > 10
    }
    pair_variance = {
        (first, second): variances[first] + variances[second]
        for first in variances
        for second in variances
        if first != second and len(all_scores[first]) > 10 and len(all_scores[second]) > 10
    }

    banned: set[str] = set()
    for user, user_lines in by_user.items():
        if len(user_lines) < 3:
            continue
        probabilities: list[float] = []
        for line in user_lines:
            annotations = line.get("annotation")
            if not isinstance(annotations, list):
                continue
            for item_annotation in annotations:
                if not isinstance(item_annotation, dict):
                    continue
                valid: list[tuple[str, float]] = []
                for system, annotation in item_annotation.items():
                    if isinstance(system, str) and isinstance(annotation, dict):
                        score = _finite_score(annotation.get("score"))
                        if score is not None:
                            valid.append((system, score))
                for index, (first, first_score) in enumerate(valid):
                    for second, second_score in valid[index + 1 :]:
                        key = (first, second)
                        if key not in pair_variance:
                            continue
                        logprob = -(
                            (first_score - second_score - pair_mean[key]) ** 2
                            / (2 * pair_variance[key] + 1e-6)
                        )
                        probabilities.append(2**logprob)
        if probabilities and statistics.mean(probabilities) < 0.75:
            banned.add(user)
    return banned


def remove_non_displayed_annotations(
    lines_by_direction: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Remove score records whose systems were absent from the shown screen.

    A cESA judgment is defined over the translations shown in ``item.tgt``.
    Removing malformed annotation keys before the user-reliability calculation
    prevents them from influencing any later decision.  The current dump has
    the same user exclusions before and after this correction, but doing it at
    this earlier point is the only generally sound order.
    """
    cleaned: dict[str, list[dict[str, Any]]] = {}
    excluded: dict[str, int] = collections.defaultdict(int)
    for direction, lines in lines_by_direction.items():
        cleaned_lines: list[dict[str, Any]] = []
        for line in lines:
            items, annotations = line.get("item"), line.get("annotation")
            if not isinstance(items, list) or not isinstance(annotations, list):
                raise ValueError(f"Malformed item/annotation lists in {direction}")
            if len(items) != len(annotations):
                raise ValueError(f"Mismatched item/annotation lists in {direction}")
            new_annotations: list[dict[str, Any]] = []
            for item, item_annotation in zip(items, annotations):
                if not isinstance(item, dict) or not isinstance(item_annotation, dict):
                    raise ValueError(f"Malformed content row in {direction}")
                targets = item.get("tgt")
                if not isinstance(targets, dict):
                    raise ValueError(f"Missing target translations in {direction}")
                screen_annotation = dict(item_annotation)
                for system in tuple(screen_annotation):
                    if system in targets:
                        continue
                    payload = screen_annotation.pop(system)
                    if isinstance(payload, dict) and _finite_score(payload.get("score")) is not None:
                        excluded[normalise_direction(direction)] += 1
                new_annotations.append(screen_annotation)
            new_line = dict(line)
            new_line["annotation"] = new_annotations
            cleaned_lines.append(new_line)
        cleaned[direction] = cleaned_lines
    return cleaned, dict(excluded)


def remove_low_reliability_users(
    lines_by_direction: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int], dict[str, set[str]]]:
    """Apply GenMT's published low-reliability-user rule per direction."""
    filtered: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, int] = {}
    banned_by_direction: dict[str, set[str]] = {}
    for direction, lines in lines_by_direction.items():
        banned = low_reliability_users(lines)
        filtered[direction] = [line for line in lines if line.get("user_id") not in banned]
        summary[direction] = len(banned)
        banned_by_direction[direction] = banned
    return filtered, summary, banned_by_direction


def normalise_direction(direction: str) -> str:
    return direction.removesuffix(" v3")


def split_item_id(item_id: str) -> tuple[str, str, int]:
    """Return (domain, bare-document-id, zero-based segment index)."""
    parts = item_id.rsplit("_###_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        raise ValueError(f"Unexpected GenMT item ID: {item_id}")
    document_part, segment_index = parts[0], int(parts[1])
    domain, bare_doc = document_part.split("_###_", 1)
    return domain, bare_doc, segment_index


def count_spans(annotation: dict[str, Any], severity: str) -> int:
    spans = annotation.get("error_spans")
    if not isinstance(spans, list):
        return 0
    return sum(isinstance(span, dict) and span.get("severity") == severity for span in spans)


def extract_item_system_evidence(
    filtered: dict[str, list[dict[str, Any]]],
) -> tuple[
    dict[tuple[str, str, int, str], dict[str, float]],
    dict[tuple[str, str, int, str], str],
    dict[str, int],
]:
    """Aggregate retained evidence and retain the exact displayed text.

    The cESA screen contains the segment text that annotators actually saw.
    For every evaluated segment we therefore preserve that text in preference
    to a later reconstruction from the whole-document submission.  Repeated
    occurrences must agree exactly; otherwise selection would be ambiguous.
    """
    observations: dict[tuple[str, str, int, str], list[tuple[float, int, int]]] = collections.defaultdict(list)
    displayed_texts: dict[tuple[str, str, int, str], set[str]] = collections.defaultdict(set)
    non_displayed_observations: dict[str, int] = collections.defaultdict(int)
    for raw_direction, lines in filtered.items():
        direction = normalise_direction(raw_direction)
        for line in lines:
            items, annotations = line.get("item"), line.get("annotation")
            if not isinstance(items, list) or not isinstance(annotations, list) or len(items) != len(annotations):
                raise ValueError(f"Malformed item/annotation lists in {raw_direction}")
            for item, item_annotation in zip(items, annotations):
                if not isinstance(item, dict) or not isinstance(item_annotation, dict):
                    raise ValueError(f"Malformed content row in {raw_direction}")
                item_id = item.get("item_id")
                if not isinstance(item_id, str):
                    raise ValueError(f"Missing item_id in content row in {raw_direction}")
                domain, bare_doc, segment_index = split_item_id(item_id)
                targets = item.get("tgt")
                if not isinstance(targets, dict):
                    raise ValueError(f"Missing target translations for {item_id}")
                for system, annotation in item_annotation.items():
                    if not isinstance(system, str) or not isinstance(annotation, dict):
                        continue
                    score = _finite_score(annotation.get("score"))
                    if score is None:
                        continue
                    key = (direction, f"{domain}_###_{bare_doc}", segment_index, system)
                    translation = targets.get(system)
                    if not isinstance(translation, str):
                        # A score for a system absent from item.tgt cannot be
                        # a score for one of the translations actually shown
                        # to the annotator.  Unlike 02b's aggregate result
                        # printer, the reference builder must not use it.
                        non_displayed_observations[direction] += 1
                        continue
                    observations[key].append((score, count_spans(annotation, "minor"), count_spans(annotation, "major")))
                    displayed_texts[key].add(translation)

    evidence = {
        key: {
            "score": statistics.mean(row[0] for row in rows),
            "minor_errors": statistics.mean(row[1] for row in rows),
            "major_errors": statistics.mean(row[2] for row in rows),
            "n_annotations": float(len(rows)),
        }
        for key, rows in observations.items()
    }
    ambiguous = {key: values for key, values in displayed_texts.items() if len(values) != 1}
    if ambiguous:
        key, values = next(iter(ambiguous.items()))
        raise ValueError(f"Conflicting displayed translations for {key}: {len(values)} variants")
    return evidence, {key: next(iter(values)) for key, values in displayed_texts.items()}, dict(non_displayed_observations)


def load_documents(data_path: Path) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """Load official WMT26 documents, indexed by direction and bare ID."""
    documents: dict[tuple[str, str], dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    with data_path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            row = json.loads(raw_line)
            doc_id = row.get("doc_id")
            if not isinstance(doc_id, str) or not doc_id.startswith("WMT26_###_"):
                continue
            parts = doc_id.removeprefix("WMT26_###_").split("_###_", 3)
            if len(parts) != 4:
                raise ValueError(f"Unexpected document ID: {doc_id}")
            domain, source, target, bare_doc = parts
            documents[(source, target)][f"{domain}_###_{bare_doc}"] = row
    return documents


def load_system_outputs(systems_dir: Path) -> dict[str, dict[str, str]]:
    """Load whole-document outputs for every submitted system."""
    outputs: dict[str, dict[str, str]] = {}
    for path in sorted(systems_dir.glob("*.jsonl")):
        by_document: dict[str, str] = {}
        with path.open(encoding="utf-8") as stream:
            for raw_line in stream:
                row = json.loads(raw_line)
                doc_id, hypothesis = row.get("doc_id"), row.get("hypothesis")
                if isinstance(doc_id, str) and isinstance(hypothesis, str):
                    by_document[doc_id] = hypothesis
        outputs[path.stem] = by_document
    return outputs


def source_segments(source: str) -> list[str]:
    """Use the public GenMT source segmentation convention."""
    text = source.strip()
    if text.startswith("```json"):
        return split_blocks(source, json_value_end_positions)
    if text.startswith("<p>"):
        return split_blocks(source, lambda value: literal_end_positions(value, "</p>"))
    return [source]


def literal_end_positions(text: str, token: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        index = text.find(token, start)
        if index < 0:
            break
        positions.append(index + len(token))
        start = index + len(token)
    return positions


def json_value_end_positions(text: str) -> list[int]:
    """Return JSON value boundaries as in GenMT's alignment utility."""
    def string_pattern(quote: str) -> re.Pattern[str]:
        escaped = re.escape(quote)
        return re.compile(rf"{escaped}(?:[^{escaped}\\]|\\.)*{escaped}")

    string_re = string_pattern('"')
    if not string_re.search(text):
        string_re = next(
            (candidate for candidate in (string_pattern("”"), string_pattern("“"), string_pattern("„")) if candidate.search(text)),
            string_re,
        )
    positions: list[int] = []
    for match in string_re.finditer(text):
        remainder = text[match.end() :]
        if re.match(r"\s*:", remainder):
            continue
        comma = re.match(r"\s*,", remainder)
        positions.append(match.end() + (comma.end() if comma else 0))
    return positions


def move_leading_newlines(blocks: list[str]) -> list[str]:
    blocks = list(blocks)
    for index in range(1, len(blocks)):
        count = len(blocks[index]) - len(blocks[index].lstrip("\n"))
        if count:
            blocks[index - 1] += blocks[index][:count]
            blocks[index] = blocks[index][count:]
    return blocks


def split_blocks(text: str, boundary_function) -> list[str]:
    positions = boundary_function(text)
    blocks: list[str] = []
    start = 0
    for end in positions:
        blocks.append(text[start:end])
        start = end
    if start < len(text):
        blocks.append(text[start:])
    return move_leading_newlines(blocks)


def chrf_score(hypothesis: str, reference: str) -> float:
    """Return the target-side chrF score used by GenMT realignment."""
    hypothesis, reference = hypothesis.strip(), reference.strip()
    if not hypothesis or not reference:
        return 0.0
    return CHRF.sentence_score(hypothesis, [reference]).score


def split_sentences(text: str) -> list[str]:
    """Match the sentence candidate boundaries in 06a-alignment.py."""
    import re

    western = r'[.!?]+["\')\]]?(?=\s|<|$)'
    cjk = r"[。!?…;‼⁇]+[」』）”’》】]?(?=\s|<|$)"
    pattern = re.compile(rf".*?(?:{western}|{cjk}|\n\n)", re.DOTALL)
    sentences = [match.group() for match in pattern.finditer(text)]
    consumed = sum(map(len, sentences))
    if text[consumed:]:
        sentences.append(text[consumed:])
    return sentences


def nearest_whitespace(text: str) -> int:
    """Return the closest whitespace boundary to the midpoint."""
    midpoint = len(text) // 2
    for offset in range(midpoint + 1):
        for candidate in (midpoint - offset, midpoint + offset):
            if 0 <= candidate < len(text) and text[candidate].isspace():
                return candidate + 1
    return midpoint


def best_split_by_position(
    hypothesis: str,
    positions: list[int],
    current_reference: str,
    next_reference: str,
) -> tuple[str, str]:
    """Split at the boundary maximizing mean chrF against two anchor blocks."""
    position = max(
        positions,
        key=lambda candidate: (
            chrf_score(hypothesis[:candidate], current_reference)
            + chrf_score(hypothesis[candidate:], next_reference)
        ) / 2,
    )
    return hypothesis[:position], hypothesis[position:]


def find_split_point(
    hypothesis: str,
    current_reference: str,
    next_reference: str,
    document_type: str,
) -> tuple[str, str]:
    """Use GenMT's target-side candidate-boundary priority order."""
    if document_type == "json":
        positions = [position for position in json_value_end_positions(hypothesis) if 0 < position < len(hypothesis)]
        if positions:
            return best_split_by_position(hypothesis, positions, current_reference, next_reference)
    else:
        sentences = split_sentences(hypothesis)
        if len(sentences) > 1:
            positions = [len("".join(sentences[:index])) for index in range(1, len(sentences))]
            return best_split_by_position(hypothesis, positions, current_reference, next_reference)
    newline_positions = [index for index, character in enumerate(hypothesis) if character == "\n"]
    if newline_positions:
        position = min(newline_positions, key=lambda candidate: abs(candidate - len(hypothesis) // 2)) + 1
    else:
        position = nearest_whitespace(hypothesis)
    return hypothesis[:position], hypothesis[position:]


def insert_breaks(hypothesis_blocks: list[str], reference_blocks: list[str], document_type: str) -> list[str]:
    """Use the exact split-first phase from GenMT's 06a alignment routine."""
    blocks = list(hypothesis_blocks)
    while len(blocks) < len(reference_blocks):
        progressed = False
        for index, block in enumerate(blocks):
            current = chrf_score(block, reference_blocks[index])
            if current >= CHRF_PARAGRAPH_THRESHOLD:
                continue
            if (
                len(block) <= len(reference_blocks[index]) * SPLIT_LENGTH_RATIO
                or len(block) - len(reference_blocks[index]) < 30
            ):
                continue
            first, second = find_split_point(block, reference_blocks[index], reference_blocks[index + 1], document_type)
            blocks[index : index + 1] = [first, second]
            progressed = True
            break
        if progressed:
            continue
        for index, block in enumerate(blocks):
            if index >= len(reference_blocks) - 1:
                break
            current = chrf_score(block, reference_blocks[index])
            if current >= CHRF_PARAGRAPH_THRESHOLD:
                continue
            first, second = find_split_point(block, reference_blocks[index], reference_blocks[index + 1], document_type)
            split_score = (chrf_score(first, reference_blocks[index]) + chrf_score(second, reference_blocks[index + 1])) / 2
            as_next_score = chrf_score(block, reference_blocks[index + 1])
            if split_score > current and split_score >= as_next_score:
                blocks[index : index + 1] = [first, second]
                progressed = True
            elif as_next_score > current:
                blocks[index:index] = [""]
                progressed = True
            if progressed:
                break
        if not progressed:
            break
    return blocks


def merge_blocks(reference_blocks: list[str], hypothesis_blocks: list[str]) -> list[str]:
    """Use the same chrF dynamic-programming merge as GenMT alignment."""
    source_count, target_count = len(reference_blocks), len(hypothesis_blocks)
    if target_count <= source_count:
        return hypothesis_blocks
    matrix = np.full((source_count + 1, target_count + 1), -np.inf)
    matrix[0, 0] = 0.0
    traceback: dict[tuple[int, int], int] = {}
    for source_index in range(1, source_count + 1):
        for target_index in range(source_index, target_count - source_count + source_index + 1):
            for previous in range(source_index - 1, target_index):
                if matrix[source_index - 1, previous] == -np.inf:
                    continue
                merged = "".join(hypothesis_blocks[previous:target_index])
                score = matrix[source_index - 1, previous] + chrf_score(merged, reference_blocks[source_index - 1])
                if score > matrix[source_index, target_index]:
                    matrix[source_index, target_index] = score
                    traceback[(source_index, target_index)] = previous
    blocks: list[str] = []
    source_index, target_index = source_count, target_count
    while source_index > 0:
        previous = traceback[(source_index, target_index)]
        blocks.append("".join(hypothesis_blocks[previous:target_index]))
        target_index, source_index = previous, source_index - 1
    blocks.reverse()
    return blocks


def realign_blocks(reference_blocks: list[str], hypothesis: str, document_type: str) -> list[str]:
    """Losslessly realign a candidate using GenMT's chrF anchor procedure."""
    boundary = json_value_end_positions if document_type == "json" else lambda value: literal_end_positions(value, "</p>")
    hypothesis_blocks = split_blocks(hypothesis, boundary) or ([hypothesis] if hypothesis.strip() else [""])
    if len(hypothesis_blocks) < len(reference_blocks):
        result = insert_breaks(hypothesis_blocks, reference_blocks, document_type)
    else:
        result = merge_blocks(reference_blocks, hypothesis_blocks)
    result = move_leading_newlines(result)
    if len(result) < len(reference_blocks):
        result += [""] * (len(reference_blocks) - len(result))
    elif len(result) > len(reference_blocks):
        result = result[: len(reference_blocks) - 1] + ["".join(result[len(reference_blocks) - 1 :])]
    return result


def document_segments(
    document: dict[str, Any],
    system: str,
    outputs: dict[str, dict[str, str]],
    cache: dict[tuple[str, str], list[str]],
) -> list[str]:
    """Return a lossless source-aligned candidate translation for one document."""
    doc_id = document["doc_id"]
    key = (system, doc_id)
    if key in cache:
        return cache[key]
    if system in HUMAN_MODEL_TO_REFERENCE_KEY:
        hypothesis = document.get("refs", {}).get(HUMAN_MODEL_TO_REFERENCE_KEY[system])
    else:
        hypothesis = outputs.get(system, {}).get(doc_id)
        if hypothesis is None and f"{system} with-reasoning" in outputs:
            hypothesis = outputs[f"{system} with-reasoning"].get(doc_id)
    if not isinstance(hypothesis, str):
        raise KeyError(f"No output for {system!r} / {doc_id}")

    source = document.get("src_text")
    if not isinstance(source, str):
        raise ValueError(f"Missing source text: {doc_id}")
    expected = source_segments(source)
    stripped = source.strip()
    if len(expected) == 1:
        segments = [hypothesis]
    else:
        is_json = stripped.startswith("```json")
        boundary = json_value_end_positions if is_json else lambda value: literal_end_positions(value, "</p>")
        direct = split_blocks(hypothesis, boundary)
        if len(direct) == len(expected):
            segments = direct
        else:
            # This is the same target-language chrF anchor used by GenMT's
            # 06a-alignment.py.  Source segments cannot serve as a valid
            # chrF reference because they are in a different language.
            anchor = outputs.get("GPT 5.5", {}).get(doc_id)
            if not isinstance(anchor, str):
                raise KeyError(f"Missing GPT 5.5 alignment anchor for {doc_id}")
            anchor_segments = split_blocks(anchor, boundary)
            if len(anchor_segments) != len(expected):
                raise ValueError(
                    f"GPT 5.5 anchor is not source-aligned for {doc_id}: "
                    f"{len(anchor_segments)} target blocks, {len(expected)} source segments"
                )
            segments = realign_blocks(
                anchor_segments,
                hypothesis,
                "json" if is_json else "html",
            )
    if len(segments) != len(expected) or "".join(segments) != hypothesis:
        raise ValueError(f"Non-lossless segmentation for {system!r} / {doc_id}")
    cache[key] = segments
    return segments


def candidate_sort_key(evidence: dict[str, float], system: str) -> tuple[float, float, float, str]:
    """Return the deterministic ascending sort key for candidate quality.

    Lower is better here so that :func:`min` can express all tie breaks
    clearly: higher cESA, fewer major-error spans, more annotations, then the
    lexical system name.  The final criterion makes results reproducible even
    when all human-derived quantities are equal.
    """
    return (
        -evidence["score"],
        evidence["major_errors"],
        -evidence["n_annotations"],
        system,
    )


def best_candidate(candidates: dict[str, dict[str, float]]) -> str:
    """Return the highest-quality candidate under the published tie breaks."""
    if not candidates:
        raise ValueError("Cannot select from an empty candidate set")
    return min(
        candidates,
        key=lambda system: candidate_sort_key(candidates[system], system),
    )


def is_strict_quality_improvement(
    candidate: dict[str, float], incumbent: dict[str, float]
) -> bool:
    """Return whether cESA and major-error evidence strictly improve.

    Annotation count and system name make an otherwise exact selection tie
    reproducible, but are not quality evidence. They therefore cannot alone
    cause a document segment to be replaced.
    """
    return candidate["score"] > incumbent["score"] or (
        candidate["score"] == incumbent["score"]
        and candidate["major_errors"] < incumbent["major_errors"]
    )


def select_references(
    evidence: dict[tuple[str, str, int, str], dict[str, float]],
    displayed_texts: dict[tuple[str, str, int, str], str],
    documents: dict[tuple[str, str], dict[str, dict[str, Any]]],
    outputs: dict[str, dict[str, str]],
    score_floor: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Select hybrid synthetic references and return output/provenance/stats rows."""
    by_document: dict[tuple[str, str], dict[str, dict[int, dict[str, dict[str, float]]]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(dict))
    )
    for (direction, doc_key, segment_index, system), item_evidence in evidence.items():
        source, target = direction.split("---")
        by_document[(source, target)][doc_key][segment_index][system] = item_evidence

    cache: dict[tuple[str, str], list[str]] = {}
    output_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    direction_rows: list[dict[str, Any]] = []

    for language_pair, docs_with_evidence in sorted(by_document.items()):
        source, target = language_pair
        if language_pair not in documents:
            raise KeyError(f"No GenMT documents for {source}---{target}")
        direction_stats: dict[str, list[float]] = collections.defaultdict(list)
        for doc_key, segment_candidates in sorted(docs_with_evidence.items()):
            document = documents[language_pair].get(doc_key)
            if document is None:
                raise KeyError(f"No document for {source}---{target} / {doc_key}")
            expected_segments = source_segments(document["src_text"])
            candidate_doc_evidence: dict[str, list[dict[str, float]]] = collections.defaultdict(list)
            for candidates in segment_candidates.values():
                for system, item_evidence in candidates.items():
                    candidate_doc_evidence[system].append(item_evidence)
            summaries = {
                system: {
                    "score": statistics.mean(row["score"] for row in rows),
                    "major_errors": statistics.mean(row["major_errors"] for row in rows),
                    "n_annotations": statistics.mean(row["n_annotations"] for row in rows),
                    "coverage": float(len(rows)),
                }
                for system, rows in candidate_doc_evidence.items()
            }
            # A document-level selection is meaningful only if the candidate
            # has been assessed on every segment in that document.  The final
            # release happens to have at least one such candidate for every
            # document.  Fail rather than silently selecting a candidate from
            # an easier subset should that cease to hold in a later dump.
            complete_summaries = {
                system: summary
                for system, summary in summaries.items()
                if summary["coverage"] == len(expected_segments)
            }
            if not complete_summaries:
                raise ValueError(
                    "No fully assessed candidate for "
                    f"{source}---{target} / {document['doc_id']}"
                )
            selected_document_system = best_candidate(complete_summaries)
            document_translation = document_segments(document, selected_document_system, outputs, cache)
            if len(document_translation) != len(expected_segments):
                raise ValueError(f"Segment count mismatch after alignment: {document['doc_id']}")

            selected_segments = list(document_translation)
            replacements = 0
            observed_selected_scores: list[float] = []
            observed_selected_majors: list[float] = []
            for segment_index in range(len(expected_segments)):
                candidates = segment_candidates.get(segment_index, {})
                selected_evidence = candidates.get(selected_document_system)
                final_system = selected_document_system
                final_evidence = selected_evidence
                trigger = "not_scored"
                if selected_evidence is not None:
                    text_key = (f"{source}---{target}", doc_key, segment_index, selected_document_system)
                    selected_segments[segment_index] = displayed_texts[text_key]
                    observed_selected_scores.append(selected_evidence["score"])
                    observed_selected_majors.append(selected_evidence["major_errors"])
                    if selected_evidence["score"] < score_floor:
                        trigger = "score_below_80"
                    elif selected_evidence["major_errors"] > 0:
                        trigger = "major_error"
                    else:
                        trigger = "retain"
                    if trigger != "retain":
                        local_system = best_candidate(candidates)
                        if is_strict_quality_improvement(
                            candidates[local_system], selected_evidence
                        ):
                            final_system = local_system
                            final_evidence = candidates[local_system]
                            text_key = (f"{source}---{target}", doc_key, segment_index, local_system)
                            selected_segments[segment_index] = displayed_texts[text_key]
                            replacements += 1
                provenance_rows.append({
                    "direction": f"{source}---{target}",
                    "doc_id": document["doc_id"],
                    "document_key": doc_key,
                    "segment_index": segment_index,
                    "document_selected_system": selected_document_system,
                    "document_score": summaries[selected_document_system]["score"],
                    "document_major_errors": summaries[selected_document_system]["major_errors"],
                    "document_annotated_segments": int(summaries[selected_document_system]["coverage"]),
                    "document_total_segments": len(expected_segments),
                    "selection_action": "replaced" if final_system != selected_document_system else trigger,
                    "final_system": final_system,
                    "selected_score": selected_evidence["score"] if selected_evidence else "",
                    "selected_major_errors": selected_evidence["major_errors"] if selected_evidence else "",
                    "final_score": final_evidence["score"] if final_evidence else "",
                    "final_major_errors": final_evidence["major_errors"] if final_evidence else "",
                    "final_annotations": int(final_evidence["n_annotations"]) if final_evidence else "",
                })
                if final_evidence is not None:
                    direction_stats["final_scores"].append(final_evidence["score"])
                    direction_stats["final_major_errors"].append(final_evidence["major_errors"])
            output_rows.append({
                "doc_id": document["doc_id"],
                "source": document["src_text"],
                "direction": f"{source}---{target}",
                "hypothesis": "".join(selected_segments),
                "hypothesis_segmented": selected_segments,
                "metadata": {
                    "selection": "cESA document selection with segment repair",
                    "document_selected_system": selected_document_system,
                    "document_cesa": summaries[selected_document_system]["score"],
                    "document_mean_major_errors": summaries[selected_document_system]["major_errors"],
                    "document_annotated_segments": int(summaries[selected_document_system]["coverage"]),
                    "document_total_segments": len(expected_segments),
                    "replaced_segments": replacements,
                },
            })
            direction_stats["documents"].append(1.0)
            direction_stats["all_segments"].append(float(len(expected_segments)))
            direction_stats["replacements"].append(float(replacements))
            direction_stats["doc_scores"].append(summaries[selected_document_system]["score"])
            direction_stats["doc_coverage"].append(summaries[selected_document_system]["coverage"] / len(expected_segments))

        direction_rows.append({
            "direction": f"{source}---{target}",
            "documents": int(sum(direction_stats["documents"])),
            "segments": int(sum(direction_stats["all_segments"])),
            "replaced_segments": int(sum(direction_stats["replacements"])),
            "replaced_percent": 100 * sum(direction_stats["replacements"]) / sum(direction_stats["all_segments"]),
            "mean_document_selection_cesa": statistics.mean(direction_stats["doc_scores"]),
            "mean_document_candidate_coverage": statistics.mean(direction_stats["doc_coverage"]),
            "observed_final_segments": len(direction_stats["final_scores"]),
            "mean_final_cesa": statistics.mean(direction_stats["final_scores"]),
            "mean_final_major_errors": statistics.mean(direction_stats["final_major_errors"]),
        })
    return output_rows, provenance_rows, direction_rows


def validate_release(
    output_rows: list[dict[str, Any]],
    provenance_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Fail unless the generated reference and provenance are lossless.

    This independent final check makes the release contract explicit: one
    unique document row, exactly one provenance row per source segment, and a
    hypothesis whose segment concatenation is unchanged.
    """
    document_ids = [row.get("doc_id") for row in output_rows]
    if any(not isinstance(doc_id, str) for doc_id in document_ids):
        raise ValueError("Every generated row must have a string document ID")
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("Synthetic-reference output contains duplicate documents")

    provenance_by_document: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in provenance_rows:
        doc_id = row.get("doc_id")
        if not isinstance(doc_id, str):
            raise ValueError("Every provenance row must have a string document ID")
        provenance_by_document[doc_id].append(row)

    for row in output_rows:
        doc_id = row["doc_id"]
        source = row.get("source")
        segments = row.get("hypothesis_segmented")
        hypothesis = row.get("hypothesis")
        if not isinstance(source, str) or not isinstance(hypothesis, str):
            raise ValueError(f"Malformed synthetic-reference row: {doc_id}")
        if not isinstance(segments, list) or not all(isinstance(segment, str) for segment in segments):
            raise ValueError(f"Malformed segmented hypothesis: {doc_id}")
        expected_count = len(source_segments(source))
        if len(segments) != expected_count or "".join(segments) != hypothesis:
            raise ValueError(f"Synthetic reference is not lossless: {doc_id}")
        document_provenance = provenance_by_document.pop(doc_id, [])
        indices = sorted(row.get("segment_index") for row in document_provenance)
        if indices != list(range(expected_count)):
            raise ValueError(f"Incomplete segment provenance: {doc_id}")
    if provenance_by_document:
        raise ValueError("Provenance contains documents absent from reference output")
    return len(output_rows), len(provenance_rows)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def display_direction(direction: str) -> str:
    """Render one internal language direction for the public release README."""
    source, target = direction.split("---")
    return f"{LANGUAGE_NAMES[source]} → {LANGUAGE_NAMES[target]}"


def write_release_readme(
    output_dir: Path,
    provenance_rows: list[dict[str, Any]],
    direction_rows: list[dict[str, Any]],
    non_displayed_score_observations: int,
) -> None:
    """Write the human-readable release README and its result summary."""
    actions = collections.Counter(str(row["selection_action"]) for row in provenance_rows)
    selected_scores = [float(row["selected_score"]) for row in provenance_rows if row["selected_score"] != ""]
    final_scores = [float(row["final_score"]) for row in provenance_rows if row["final_score"] != ""]
    selected_majors = [float(row["selected_major_errors"]) for row in provenance_rows if row["selected_major_errors"] != ""]
    final_majors = [float(row["final_major_errors"]) for row in provenance_rows if row["final_major_errors"] != ""]
    documents = len({str(row["doc_id"]) for row in provenance_rows})
    segments = len(provenance_rows)
    replacements = actions["replaced"]
    triggered = replacements + actions["score_below_80"] + actions["major_error"]
    directions = len(direction_rows)

    report = f"""# WMT26 synthetic references

This release contains one complete synthetic reference for every document with
retained official WMT26 General MT cESA evidence: **{documents:,} documents**,
**{segments:,} source segments**, and **{directions} directions**.

## Selection procedure

1. Apply the published GenMT annotation processing: authoritative RESET
   handling, exclusion of tutorial and attention-check items, and the
   low-reliability-annotator filter.
2. Exclude {non_displayed_score_observations:,} score records for translations not present in the corresponding screen's displayed target set. These cannot be valid cESA observations for the translation in question.
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

The repair condition was met on {triggered:,} segments; {replacements:,}
segments ({100 * replacements / segments:.2f}%) were replaced by a better
locally observed translation. On the same evidence used for selection, the
mean cESA score increases from {statistics.mean(selected_scores):.2f} for the
document-only selection to {statistics.mean(final_scores):.2f} after repair,
and the mean major-error count decreases from {statistics.mean(selected_majors):.3f}
to {statistics.mean(final_majors):.3f}. These are in-sample descriptive
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
{chr(10).join(f"| {display_direction(str(row['direction']))} | {float(row['mean_final_cesa']):.2f} |" for row in direction_rows)}
"""
    (output_dir / "README.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--score-floor", type=float, default=SCORE_FLOOR)
    args = parser.parse_args()
    if not 0 <= args.score_floor <= 100:
        parser.error("--score-floor must be in [0, 100]")
    if not args.annotations.is_file():
        parser.error(f"Annotations not found: {args.annotations}")
    if not (args.data_dir / "wmt26-genmt.jsonl").is_file():
        parser.error(f"Missing GenMT document data under: {args.data_dir}")
    if not (args.data_dir / "systems").is_dir():
        parser.error(f"Missing system outputs under: {args.data_dir / 'systems'}")

    with args.annotations.open(encoding="utf-8") as stream:
        raw = json.load(stream)
    if not isinstance(raw, dict):
        raise ValueError("Annotation dump must be a direction-to-lines JSON object")
    raw = {str(direction): lines for direction, lines in raw.items() if isinstance(lines, list)}
    reset_filtered = apply_resets_and_remove_noncontent(raw)
    legacy_bans = {
        direction: low_reliability_users(lines)
        for direction, lines in reset_filtered.items()
    }
    screen_valid, non_displayed_observations = remove_non_displayed_annotations(
        reset_filtered
    )
    filtered, removed_users, screen_valid_bans = remove_low_reliability_users(
        screen_valid
    )
    reliability_decision_changes = {
        direction: {
            "without_screen_validation": sorted(legacy_bans[direction]),
            "with_screen_validation": sorted(screen_valid_bans[direction]),
        }
        for direction in legacy_bans
        if legacy_bans[direction] != screen_valid_bans[direction]
    }
    evidence, displayed_texts, defensive_non_displayed_observations = (
        extract_item_system_evidence(filtered)
    )
    if defensive_non_displayed_observations:
        raise AssertionError(
            "Screen validation should have removed every non-displayed score: "
            f"{defensive_non_displayed_observations}"
        )
    documents = load_documents(args.data_dir / "wmt26-genmt.jsonl")
    outputs = load_system_outputs(args.data_dir / "systems")
    output_rows, provenance_rows, direction_rows = select_references(
        evidence,
        displayed_texts,
        documents,
        outputs,
        args.score_floor,
    )
    validated_documents, validated_segments = validate_release(output_rows, provenance_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference_path = args.output_dir / "wmt26_synthetic_references.jsonl"
    with reference_path.open("w", encoding="utf-8") as stream:
        for row in output_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_csv(args.output_dir / "segment_provenance.csv", provenance_rows)
    write_csv(args.output_dir / "direction_summary.csv", direction_rows)
    manifest = {
        "method": "cESA document selection with segment repair",
        "score_floor": args.score_floor,
        "major_error_trigger": "mean major-error count greater than zero",
        "document_selection_tie_breaks": [
            "higher average cESA",
            "fewer average major errors",
            "more annotations",
            "lexical system name",
        ],
        "segment_repair_rule": (
            "replace only for higher average cESA, or equal average cESA "
            "with fewer average major errors"
        ),
        "annotations": str(args.annotations.resolve()),
        "documents": str((args.data_dir / "wmt26-genmt.jsonl").resolve()),
        "system_outputs": str((args.data_dir / "systems").resolve()),
        "filtered_directions": len(filtered),
        "screen_validation_before_reliability_filter": True,
        "reliability_decisions_changed_by_screen_validation": reliability_decision_changes,
        "low_reliability_users_removed": removed_users,
        "non_displayed_score_observations_excluded": non_displayed_observations,
        "references": reference_path.name,
        "provenance": "segment_provenance.csv",
        "summary": "direction_summary.csv",
        "warning": "The reported selected cESA statistics are in-sample descriptive values, not held-out reference-quality estimates.",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_release_readme(
        args.output_dir,
        provenance_rows,
        direction_rows,
        sum(non_displayed_observations.values()),
    )
    print(
        "Validated "
        f"{validated_documents:,} complete documents / "
        f"{validated_segments:,} lossless segments."
    )
    print(f"Wrote {len(output_rows)} synthetic-reference documents to {reference_path}")
    print(f"Wrote {len(provenance_rows)} provenance rows and {len(direction_rows)} direction summaries to {args.output_dir}")


if __name__ == "__main__":
    main()
