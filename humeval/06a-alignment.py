from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from sacrebleu import CHRF

LOG_FILE = Path("alignment.log")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = SCRIPT_DIR / "../../wmt26-generalmt-internal/blindset/release.jsonl"
DEFAULT_TRANSLATION = SCRIPT_DIR / "../../wmt26-generalmt-internal/submissions"
DEFAULT_MAPPING = SCRIPT_DIR / "../../wmt26-generalmt-internal/blindset/doc_id_mapping.jsonl"
DEFAULT_REFERENCE = SCRIPT_DIR / "../../wmt26-generalmt-internal/submissions/GPT 5.5.jsonl"

# chrF at/above this counts as "already aligned".
CHRF_PARAGRAPH_THRESHOLD = 85.0

# tgt must be this many times longer than ref 
# before insert_breaks will split it 
SPLIT_LENGTH_RATIO = 1.3

def _json_string_token_pattern(quote: str) -> str:
    esc = re.escape(quote)
    return rf'{esc}(?:[^{esc}\\]|\\.)*{esc}'


_JSON_STRING_TOKEN_RE = re.compile(_json_string_token_pattern('"'))

# some MT systems substitute a typographic quote for every '"'
_ALT_JSON_QUOTE_CHARS = ("”", "“", "„")
_ALT_JSON_STRING_TOKEN_RES = [re.compile(_json_string_token_pattern(q)) for q in _ALT_JSON_QUOTE_CHARS]


def _json_value_end_positions(text: str) -> list[int]:
    """Positions right after each json string VALUE (not key) in `text`"""
    token_re = _JSON_STRING_TOKEN_RE
    if not token_re.search(text):
        token_re = next((r for r in _ALT_JSON_STRING_TOKEN_RES if r.search(text)), token_re)

    positions = []
    for m in token_re.finditer(text):
        end = m.end()
        if re.match(r"\s*:", text[end:]):
            continue  # this token is a key, not a value
        comma = re.match(r"\s*,", text[end:])
        positions.append(end + (comma.end() if comma else 0))
    return positions


def _regex_end_positions(pattern: str):
    compiled = re.compile(pattern)
    return lambda text: [m.end() for m in compiled.finditer(text)]

BOUNDARY = {
    "html": _regex_end_positions(re.escape("</p>")),
    "json": _json_value_end_positions,
}

_chrf = CHRF()

_WESTERN_SENTENCE_END = r'[.!?]+["\')\]]?(?=\s|<|$)'
_CJK_SENTENCE_END = "[\u3002!?\u2026;\u203c\u2047]+[\u300d\u300f\uff09\u201d\u2019\u300b\u3011]?(?=\\s|<|$)"
_SENTENCE_RE = re.compile(rf'.*?(?:{_WESTERN_SENTENCE_END}|{_CJK_SENTENCE_END}|\n\n)', re.DOTALL)


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_jsonl(path: Path) -> dict[str, dict]:
    return {entry["doc_id"]: entry for entry in _iter_jsonl(path)}


def load_doc_meta(path: Path) -> dict[str, dict]:
    """release_doc_id -> {is_wmt26, domain, internal_doc_id}"""
    meta = {}
    for entry in _iter_jsonl(path):
        iid = entry.get("internal_doc_id") or ""
        is_wmt26 = "WMT26" in iid
        domain = entry.get("domain")
        if domain is None and is_wmt26:
            parts = iid.split("###")
            domain = parts[1].strip("_ ") if len(parts) > 1 else None
        meta[entry["release_doc_id"]] = {"is_wmt26": is_wmt26, "domain": domain, "internal_doc_id": iid}
    return meta


def _move_leading_newlines(blocks: list[str]) -> list[str]:
    """Move any leading '\\n' characters on a segment to the end of the
    previous segment instead."""
    blocks = list(blocks)
    for i in range(1, len(blocks)):
        j = 0
        while j < len(blocks[i]) and blocks[i][j] == "\n":
            j += 1
        if j:
            blocks[i - 1] += blocks[i][:j]
            blocks[i] = blocks[i][j:]
    return blocks


def split_blocks(text: str, boundary) -> list[str]:
    """Split text into an ordered, lossless partition, each block ending
    right after a position from `boundary(text)`."""
    parts = []
    pos = 0
    for end in boundary(text):
        parts.append(text[pos:end])
        pos = end
    if pos < len(text):
        parts.append(text[pos:])
    return _move_leading_newlines(parts)


def split_sentences(text: str) -> list[str]:
    sents = [m.group() for m in _SENTENCE_RE.finditer(text)]
    consumed = sum(len(s) for s in sents)
    remainder = text[consumed:]
    if remainder:
        sents.append(remainder)
    return sents


def chrf_score(hyp: str, ref: str) -> float:
    hyp, ref = hyp.strip(), ref.strip()
    if not hyp or not ref:
        return 0.0
    return _chrf.sentence_score(hyp, [ref]).score


def _nearest_whitespace_split(text: str) -> int:
    """Index just after the whitespace character closest to the mid-point of
    `text`, so a forced split doesn't land inside a word. Falls back to the
    raw mid-point if `text` has no whitespace at all (e.g. dense Thai)."""
    mid = len(text) // 2
    for offset in range(mid + 1):
        for cand in (mid - offset, mid + offset):
            if 0 <= cand < len(text) and text[cand].isspace():
                return cand + 1
    return mid


def _best_split_by_position(
    tgt_block: str, positions: list[int], ref_current: str, ref_next: str
) -> tuple[str, str]:
    """Among candidate cut `positions` in tgt_block, return the split whose
    two halves maximize combined chrF against ref_current/ref_next."""
    best_pos, best_score = positions[0], -1.0
    for pos in positions:
        score = (chrf_score(tgt_block[:pos], ref_current) +
                 chrf_score(tgt_block[pos:], ref_next)) / 2
        if score > best_score:
            best_score = score
            best_pos = pos
    return tgt_block[:best_pos], tgt_block[best_pos:]


def find_split_point(
    tgt_block: str, ref_block_current: str, ref_block_next: str, doc_type: str
) -> tuple[str, str]:
    """Split tgt_block at the candidate boundary that maximizes the combined
    chrF of both halves against their respective reference blocks."""
    if doc_type == "json":
        positions = [p for p in _json_value_end_positions(tgt_block) if 0 < p < len(tgt_block)]
        if positions:
            return _best_split_by_position(tgt_block, positions, ref_block_current, ref_block_next)
    else:
        sents = split_sentences(tgt_block)
        if len(sents) > 1:
            positions = [len("".join(sents[:k])) for k in range(1, len(sents))]
            return _best_split_by_position(tgt_block, positions, ref_block_current, ref_block_next)

    # no candidate boundary found 
    nl_positions = [mo.start() for mo in re.finditer(r"\n", tgt_block)]
    if nl_positions:
        mid = len(tgt_block) // 2
        pos = min(nl_positions, key=lambda p: abs(p - mid)) + 1
    else:
        pos = _nearest_whitespace_split(tgt_block)
    return tgt_block[:pos], tgt_block[pos:]


def insert_breaks(tgt_blocks: list[str], ref_blocks: list[str], doc_type: str) -> list[str]:
    """tgt has fewer blocks than ref."""
    tgt_blocks = list(tgt_blocks)
    while len(tgt_blocks) < len(ref_blocks):
        progressed = False
        for i in range(len(tgt_blocks)):
            score = chrf_score(tgt_blocks[i], ref_blocks[i])

            # the block looks aligned enough; move on to the next one
            if score >= CHRF_PARAGRAPH_THRESHOLD:
                continue

            tgt_chars = len(tgt_blocks[i])
            ref_chars = len(ref_blocks[i]) or 1
            if tgt_chars <= ref_chars * SPLIT_LENGTH_RATIO or tgt_chars - ref_chars < 30:
                continue  # not meaningfully longer than ref; skip to look further

            part1, part2 = find_split_point(tgt_blocks[i], ref_blocks[i], ref_blocks[i + 1], doc_type)
            tgt_blocks[i:i + 1] = [part1, part2]
            progressed = True
            break
        if progressed:
            continue
        
        for i in range(len(tgt_blocks)):
            if i >= len(ref_blocks) - 1:
                break  # no ref[i + 1] to compare against; nothing left to force
            current_score = chrf_score(tgt_blocks[i], ref_blocks[i])
            if current_score >= CHRF_PARAGRAPH_THRESHOLD:
                continue

            part1, part2 = find_split_point(tgt_blocks[i], ref_blocks[i], ref_blocks[i + 1], doc_type)
            split_score = (chrf_score(part1, ref_blocks[i]) +
                           chrf_score(part2, ref_blocks[i + 1])) / 2
            whole_as_next_score = chrf_score(tgt_blocks[i], ref_blocks[i + 1])

            if split_score > current_score and split_score >= whole_as_next_score:
                tgt_blocks[i:i + 1] = [part1, part2]
                progressed = True
            elif whole_as_next_score > current_score:
                tgt_blocks[i:i] = [""]
                progressed = True
            if progressed:
                break
        if not progressed:
            break
    return tgt_blocks


def merge_blocks(ref_blocks: list[str], tgt_blocks: list[str]) -> list[str]:
    """Find the globally optimal merging of tgt_blocks to match len(ref_blocks)
    using dynamic programming over all possible consecutive groupings."""
    I, J = len(ref_blocks), len(tgt_blocks)
    if J <= I:
        return tgt_blocks

    dp = np.full((I + 1, J + 1), -np.inf)
    dp[0][0] = 0.0
    traceback: dict[tuple[int, int], int] = {}

    for i in range(1, I + 1):
        # j must leave at least (I-i) blocks for the remaining ref blocks
        for j in range(i, J - I + i + 1):
            for k in range(i - 1, j):
                if dp[i - 1][k] == -np.inf:
                    continue
                merged = "".join(tgt_blocks[k:j])
                score = chrf_score(merged, ref_blocks[i - 1])
                total = dp[i - 1][k] + score
                if total > dp[i][j]:
                    dp[i][j] = total
                    traceback[(i, j)] = k

    result = []
    curr_i, curr_j = I, J
    while curr_i > 0:
        prev_j = traceback[(curr_i, curr_j)]
        result.append("".join(tgt_blocks[prev_j:curr_j]))
        curr_j = prev_j
        curr_i -= 1
    result.reverse()
    return result


def realign(ref_text: str, tgt_text: str, boundary: str, doc_type: str) -> list[str]:
    """Resegment `tgt_text` using the reference hypothesis `ref_text` (same
    target language) as the chrF anchor"""
    ref_blocks = split_blocks(ref_text, boundary)

    tgt_blocks = split_blocks(tgt_text, boundary) or ([tgt_text] if tgt_text.strip() else [""])
    num_groups = len(ref_blocks)

    if len(tgt_blocks) < num_groups:
        result = insert_breaks(tgt_blocks, ref_blocks, doc_type)
    else:
        result = merge_blocks(ref_blocks, tgt_blocks)

    result = _move_leading_newlines(result)

    if len(result) < num_groups:
        result = result + [""] * (num_groups - len(result))
    elif len(result) > num_groups:
        result = result[:num_groups - 1] + ["".join(result[num_groups - 1:])]
    return result


def process_translation_file(
    translation_path: Path,
    source_docs: dict,
    doc_meta: dict,
    reference_docs: dict,
    output_path: Path,
    log_path: Path,
) -> str:
    target_docs = load_jsonl(translation_path)

    extra_in_translation = sorted(set(target_docs) - set(source_docs))
    if extra_in_translation:
        raise ValueError(
            f"{len(extra_in_translation)} doc_id(s) in {translation_path} are missing from source: "
            f"{extra_in_translation}"
        )

    common = sorted(set(source_docs) & set(target_docs))
    missing_in_translation = sorted(set(source_docs) - set(target_docs))
    missing_wmt26 = sum(
        1 for doc_id in missing_in_translation if doc_meta.get(doc_id, {}).get("is_wmt26")
    )

    def make_row(doc_id, segments, aligned_flag):
        return {
            **target_docs[doc_id],
            "hypothesis_segmented": segments,
            "aligned": aligned_flag,
            "internal_doc_id": doc_meta.get(doc_id, {}).get("internal_doc_id"),
        }

    log_lines = []
    checked = aligned = misaligned = skipped = realigned = 0
    output_rows = []

    for doc_id in common:
        meta = doc_meta.get(doc_id, {"is_wmt26": False, "domain": None, "internal_doc_id": None})
        if not meta["is_wmt26"]:
            continue  # aligned/misaligned tracking is scoped to WMT26 docs only

        src_text = source_docs[doc_id]["source_doc"]
        tgt_text = target_docs[doc_id]["hypothesis"]

        if tgt_text == "FAILED":
            # generation failed upstream -- nothing to align against
            if src_text.strip().startswith("```json"):
                src_count = len(split_blocks(src_text, BOUNDARY["json"]))
            elif src_text.strip().startswith("<p>"):
                src_count = len(split_blocks(src_text, BOUNDARY["html"]))
            else:
                src_count = 1
            checked += 1
            misaligned += 1
            realigned += 1
            segments = ["FAILED"] + [""] * (src_count - 1)
            output_rows.append(make_row(doc_id, segments, True))
            line = f"MISALIGNED {doc_id}: target=FAILED -> REALIGNED (failed generation, {src_count} segments)"
            print(line)
            log_lines.append(line)
            continue

        if meta["domain"] == "speech":
            # speech has no paragraph/json structure to align against, so
            # treat the whole hypothesis as one segment and count it as
            # already aligned.
            checked += 1
            aligned += 1
            output_rows.append(make_row(doc_id, [tgt_text], False))
            continue

        if src_text.strip().startswith("```json"):
            doc_type = "json"
        elif src_text.strip().startswith("<p>"):
            doc_type = "html"
        else:
            skipped += 1
            continue
        boundary = BOUNDARY[doc_type]
        src_count = len(split_blocks(src_text, boundary))
        tgt_blocks = split_blocks(tgt_text, boundary)
        tgt_count = len(tgt_blocks)

        checked += 1
        if src_count == tgt_count:
            aligned += 1
            output_rows.append(make_row(doc_id, tgt_blocks, False))
            continue

        misaligned += 1

        ref_text = reference_docs.get(doc_id, {}).get("hypothesis", "")
        segments = realign(ref_text, tgt_text, boundary, doc_type)

        assert len(segments) == src_count, (
            f"realignment failed for {doc_id}: "
            f"expected {src_count} segments, got {len(segments)}"
        )
        realigned += 1
        output_rows.append(make_row(doc_id, segments, True))
        direction = "split" if tgt_count < src_count else "merge"
        line = f"MISALIGNED {doc_id}: {doc_type} source={src_count} target={tgt_count} -> REALIGNED ({direction} to {len(segments)} segments)"

        print(line)
        log_lines.append(line)

    summary = (
        f"WMT26: {checked} checked, {aligned} aligned, {misaligned} misaligned ({realigned} realigned), "
        f"{skipped} skipped ({len(missing_in_translation)} missing from translation file, "
        f"{missing_wmt26} WMT26)"
    )
    print(summary)
    log_lines.append(summary)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"\nWrote log to {log_path}")

    if output_rows:
        df = pd.DataFrame(output_rows)
        assert df.apply(lambda x: x["hypothesis"] == "".join(x["hypothesis_segmented"]), axis=1).all()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for row in output_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {len(output_rows)} WMT26 document(s) to {output_path}")

    return summary


def main() -> None:
    global CHRF_PARAGRAPH_THRESHOLD  # may be overridden by --threshold CLI arg
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source_path", type=Path, default=DEFAULT_SOURCE,
        help=f"Path to the source .jsonl file (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--translation_path", type=Path, default=DEFAULT_TRANSLATION,
        help=(
            f"Path to a translation .jsonl file, or a directory containing "
            f"multiple .jsonl files to process in bulk (default: {DEFAULT_TRANSLATION})"
        ),
    )
    parser.add_argument(
        "--mapping_path", type=Path, default=DEFAULT_MAPPING,
        help=f"Path to doc_id_mapping.jsonl (default: {DEFAULT_MAPPING})",
    )
    parser.add_argument(
        "--reference_path", type=Path, default=DEFAULT_REFERENCE,
        help=f"Path to the GPT-5 submission .jsonl used as the chrF realignment anchor (default: {DEFAULT_REFERENCE})",
    )
    parser.add_argument(
        "--output_dir", type=Path, default=None,
        help=(
            "Directory to write realigned .jsonl file(s) into (default: "
            "<translation_path>/aligned if --translation_path is a directory, "
            "else <translation_path's parent>/aligned)"
        ),
    )
    parser.add_argument(
        "--log_dir", type=Path, default=None,
        help=(
            "Directory to write one alignment log per translation file into "
            "(default: <translation_path>/alignment_logs if --translation_path "
            "is a directory, else alignment.log in the current directory)"
        ),
    )
    parser.add_argument(
        "--threshold", type=float, default=CHRF_PARAGRAPH_THRESHOLD,
        help=(
            f"chrF paragraph-level score at/above which a paragraph pair is "
            f"considered aligned (default: {CHRF_PARAGRAPH_THRESHOLD}). "
            f"Lower = fewer pairs are treated as aligned; higher = more "
            f"pairs are examined as realignment candidates."
        ),
    )
    args = parser.parse_args()
    CHRF_PARAGRAPH_THRESHOLD = args.threshold

    source_path, translation_path, mapping_path, reference_path = (
        args.source_path, args.translation_path, args.mapping_path, args.reference_path
    )

    if not source_path.is_file():
        parser.error(f"SOURCE_JSONL does not exist:\n  {source_path}")
    if not translation_path.exists():
        parser.error(f"TRANSLATION_JSONL does not exist:\n  {translation_path}")
    if not mapping_path.is_file():
        parser.error(f"MAPPING_JSONL does not exist:\n  {mapping_path}")
    if not reference_path.is_file():
        parser.error(f"REFERENCE_JSONL does not exist:\n  {reference_path}")

    source_docs = load_jsonl(source_path)
    doc_meta = load_doc_meta(mapping_path)
    reference_docs = load_jsonl(reference_path)

    if translation_path.is_dir():
        translation_files = sorted(translation_path.glob("*.jsonl"))
        if not translation_files:
            parser.error(f"No .jsonl files found in {translation_path}")
        output_dir = args.output_dir or (translation_path / "aligned")
        log_dir = args.log_dir or (translation_path / "alignment_logs")

        results = []
        for tp in translation_files:
            print(f"\n=== {tp.name} ===")
            try:
                summary = process_translation_file(
                    tp, source_docs, doc_meta, reference_docs,
                    output_path=output_dir / tp.name,
                    log_path=log_dir / f"{tp.stem}.log",
                )
                results.append(f"{tp.name}: {summary}")
            except Exception as exc:
                print(f"ERROR processing {tp.name}: {exc}")
                results.append(f"{tp.name}: ERROR - {exc}")

        print("\n" + "\n".join(results))
    else:
        output_path = (
            (args.output_dir / translation_path.name) if args.output_dir
            else translation_path.parent / "aligned" / translation_path.name
        )
        log_path = (args.log_dir / f"{translation_path.stem}.log") if args.log_dir else LOG_FILE
        process_translation_file(
            translation_path, source_docs, doc_meta, reference_docs,
            output_path=output_path, log_path=log_path,
        )


if __name__ == "__main__":
    main()
