import csv
import math
import statistics
import itertools
import sys
from pathlib import Path
import re

SOURCE_ROOT = Path("/home/srajaee/wmt26-generalmt-internal/subsampled_documents")   # contains <src_lang> folders
TARGET_ROOT = Path("/home/srajaee/wmt26-generalmt-internal/translated_documents")   # contains <src_lang> folders
OUTPUT_ROOT = Path("edited")  

OUTPUT_CSV = Path("summary.csv")

PARAGRAPH_SEP = "\n\n" 


def align_segments_by_merging_tgt(segments_src: list[str], segments_tgt: list[str]) -> list[str]:
    import statistics
    import itertools

    # assume the target is always over-segmented
    assert len(segments_src) <= len(segments_tgt)

    fertility = sum(len(x) for x in segments_tgt) / sum(len(x) for x in segments_src)
    def size_mismatch(segments_src: list[str], segments_tgt: list[str]) -> float:
        # compute MAE between segment sizes
        return statistics.mean([abs(len(a)*fertility - len(b)) for a, b in zip(segments_src, segments_tgt)])

    # find global optimum in allocation
    # we know that we need to merge k = len(segments_tgt) - len(segments_src) segments together
    # encode each merge as ordered k numbers from [0, len(segments_tgt)-1]
    best_candidate = None
    best_mae = float("inf")
    for merge_indices in itertools.combinations(range(len(segments_tgt)-1), len(segments_tgt) - len(segments_src)):
        # go backwards so we remain valid
        merge_indices = sorted(merge_indices, reverse=True)
        segments_tgt_candidate = list(segments_tgt)
        for merge_index in merge_indices:
            segments_tgt_candidate[merge_index] += "\n" + segments_tgt_candidate.pop(merge_index + 1)
        mae = size_mismatch(segments_src, segments_tgt_candidate)
        if mae < best_mae:
            best_mae = mae
            best_candidate = segments_tgt_candidate
    
    return best_candidate

def align_segments_by_splitting_tgt(segments_src: list[str], segments_tgt: list[str]) -> list[str]:
 
    # assume the target is always under-segmented
    assert len(segments_tgt) <= len(segments_src)
 
    fertility = sum(len(x) for x in segments_tgt) / sum(len(x) for x in segments_src)
 
    western = r'[.!?]+["\')\]]?(?=\s|$)'
    cjk     = r'[。！？…；‼⁇]+[」』）”’》】]?'
    sentence_pattern = re.compile(rf'.*?(?:{western}|{cjk})', re.DOTALL)
 
    def join_sep(text: str) -> str:
        return "" if re.search(r'[\u3000-\u9fff\uff00-\uffef]', text) else " "
 
    def split_into_sentences(text: str) -> list[str]:
        sents = [m.group().strip() for m in sentence_pattern.finditer(text) if m.group().strip()]
        if not sents:
            return [text.strip()] if text.strip() else []
        consumed = sum(len(m.group()) for m in sentence_pattern.finditer(text))
        remainder = text[consumed:].strip()
        if remainder:
            sents.append(remainder)
        return sents
 
    def best_sentence_split(para: str, target_first_len: float):
        sents = split_into_sentences(para)
        if len(sents) < 2:
            return None
        sep = join_sep(para)
        best_i, best_diff = None, float("inf")
        running = 0
        for i in range(len(sents) - 1):
            running += len(sents[i]) + (len(sep) if i > 0 else 0)
            diff = abs(running - target_first_len)
            if diff < best_diff:
                best_diff, best_i = diff, i
        first = sep.join(sents[:best_i + 1])
        second = sep.join(sents[best_i + 1:])
        return first, second
 
    segments_tgt_candidate = list(segments_tgt)
    while len(segments_tgt_candidate) < len(segments_src):
        made_a_split = False
        for idx, para in enumerate(segments_tgt_candidate):
            expected = len(segments_src[idx]) * fertility
            if len(para) > expected:  # too long
                split = best_sentence_split(para, expected)
                if split is not None:
                    segments_tgt_candidate[idx:idx + 1] = [split[0], split[1]]
                    made_a_split = True
                    break
        if not made_a_split:
            return None
 
    return segments_tgt_candidate

def read_segments(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    raw = text.split("\n\n")
    return [chunk.strip() for chunk in raw if chunk.strip()]


def list_txt(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        return {}
    return {p.name: p for p in sorted(directory.glob("*.txt"))}


def subdirs(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(d.name for d in directory.iterdir() if d.is_dir())


def discover_units():
    for src_lang in subdirs(TARGET_ROOT):
        for tgt_lang in subdirs(TARGET_ROOT / src_lang):
            for model in subdirs(TARGET_ROOT / src_lang / tgt_lang):
                base = TARGET_ROOT / src_lang / tgt_lang / model
                for subcategory in subdirs(base):
                    tdir = base / subcategory
                    sdir = SOURCE_ROOT / src_lang / subcategory
                    odir = OUTPUT_ROOT / src_lang / tgt_lang / model / subcategory
                    yield src_lang, tgt_lang, model, subcategory, sdir, tdir, odir


def write_doc(path: Path, segments: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PARAGRAPH_SEP.join(segments), encoding="utf-8")


def main() -> None:
    if not SOURCE_ROOT.is_dir() or not TARGET_ROOT.is_dir():
        sys.exit(f"SOURCE_ROOT or TARGET_ROOT does not exist:\n  {SOURCE_ROOT}\n  {TARGET_ROOT}")

    rows = []

    for src_lang, tgt_lang, model, subcategory, sdir, tdir, odir in discover_units():
        src_files = list_txt(sdir)
        tgt_files = list_txt(tdir)
        common = sorted(set(src_files) & set(tgt_files))
        missing = sorted(set(src_files) ^ set(tgt_files))

        passed = merged = splitted = skipped = 0

        for name in common:
            src_segs = read_segments(src_files[name])
            tgt_segs = read_segments(tgt_files[name])
            n_src, n_tgt = len(src_segs), len(tgt_segs)
            out_path = odir / name

            if n_src == n_tgt:
                # already aligned 
                write_doc(out_path, tgt_segs)
                passed += 1
            elif n_tgt < n_src:
                # it needs newlines to be inserted
                refined_segs = align_segments_by_splitting_tgt(src_segs, tgt_segs)
                edited_path = out_path.with_name(out_path.stem + "_edited_splitted" + out_path.suffix)
                if refined_segs:
                    write_doc(edited_path, refined_segs)
                    splitted += 1
                else:
                    edited_path = out_path.with_name(out_path.stem + "_skipped" + out_path.suffix)
                    write_doc(edited_path, tgt_segs)
                    skipped += 1
            else:
                # it needs to merge pars on target side
                k = n_tgt - n_src
                n_combos = math.comb(n_tgt - 1, k)
                refined_segs = align_segments_by_merging_tgt(src_segs, tgt_segs)
                edited_path = out_path.with_name(out_path.stem + "_edited" + out_path.suffix)
                write_doc(edited_path, refined_segs)
                merged += 1

        rows.append({
            "source_lang": src_lang,
            "target_lang": tgt_lang,
            "model": model,
            "subcategory": subcategory,
            "documents_compared": len(common),
            "passed": passed,
            "merged": merged,
            "splitted": splitted,
            "skipped": skipped,
            "unmatched_files": len(missing),
        })

        print(f"{src_lang}->{tgt_lang} [{model}/{subcategory}]: "
              f"{passed} passed, {merged} merged, {splitted} splitted, "
              f"{skipped} skipped"
              f"({len(common)} compared, {len(missing)} unmatched)")

    if not rows:
        print("No matching documents found. Check SOURCE_ROOT / TARGET_ROOT.")

    fieldnames = ["source_lang", "target_lang", "model", "subcategory",
                  "documents_compared", "passed", "merged", "splitted",
                  "skipped", "unmatched_files"]
                  
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()