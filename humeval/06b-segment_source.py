from __future__ import annotations

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_PATH = SCRIPT_DIR / "../../wmt26-generalmt-internal/blindset/internal.jsonl"
OUTPUT_PATH = SCRIPT_DIR / "../../wmt26-generalmt-internal/blindset/internal_segmented.jsonl"


def _json_string_token_pattern(quote: str) -> str:
    esc = re.escape(quote)
    return rf'{esc}(?:[^{esc}\\]|\\.)*{esc}'


_JSON_STRING_TOKEN_RE = re.compile(_json_string_token_pattern('"'))
_ALT_JSON_QUOTE_CHARS = ("”", "“", "„")
_ALT_JSON_STRING_TOKEN_RES = [re.compile(_json_string_token_pattern(q)) for q in _ALT_JSON_QUOTE_CHARS]


def _json_value_end_positions(text: str) -> list[int]:
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


def segment_source(source_doc: str) -> list[str]:
    stripped = source_doc.strip()
    if stripped.startswith("```json"):
        boundary = BOUNDARY["json"]
    elif stripped.startswith("<p>"):
        boundary = BOUNDARY["html"]
    else:
        return [source_doc]
    return split_blocks(source_doc, boundary)


def main() -> None:
    count = wmt26_count = 0
    with SOURCE_PATH.open(encoding="utf-8") as fin, OUTPUT_PATH.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if "WMT26" in entry["doc_id"]:
                entry["source_doc_segmented"] = segment_source(entry["source_doc"])
                wmt26_count += 1
            else:
                entry["source_doc_segmented"] = ""
            fout.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

    print(f"Segmented {wmt26_count} WMT26 doc(s) out of {count} total")
    print(f"Wrote output to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
