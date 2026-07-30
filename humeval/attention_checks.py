import itertools
import random
import re

shuffled_words_num=5
CHAR_LEVEL_LANGS = {"jpn_Jpan", "tha_Thai", "zho_Hant", "zho_Hans"}
ATTENTION_CHECK_MODELS = {"GPT 5.5", "Cohere CAT+", "Gemini 3.1 Pro"}


# standalone brace/bracket punctuation (JSON structure) and markdown code-fence
# lines (e.g. "```json", "```"), so they're never candidates for shuffling
_STRUCTURAL_TOKEN_RE = re.compile(r"^(`{3,}\w*|[{}\[\]]+)$")


def _is_structural(token: str) -> bool:
    return bool(_STRUCTURAL_TOKEN_RE.match(token))


def _tokenize(text: str, lang: str | None) -> list[str]:
    pattern = r"\S|\s+" if lang in CHAR_LEVEL_LANGS else r"\S+|\s+"
    return re.findall(pattern, text)


def _shuffle_count(lang: str | None) -> int:
    return shuffled_words_num * 2 if lang in CHAR_LEVEL_LANGS else shuffled_words_num


def _eligible_indexes(parts: list[str]) -> list[int]:
    return [i for i, part in enumerate(parts) if not part.isspace() and not _is_structural(part)]


def shuffle_words(text: str, lang: str | None = None) -> str:
    parts = _tokenize(text, lang)
    item_indexes = _eligible_indexes(parts)
    swap_count = _shuffle_count(lang)

    assert len(item_indexes) > swap_count

    # pick distinct indices and rotate their contents by one position, so
    # every chosen word moves and no pair of swaps can cancel each other out
    chosen = random.sample(item_indexes, swap_count)
    values = [parts[i] for i in chosen]
    for i, value in zip(chosen, values[1:] + values[:1]):
        parts[i] = value

    return "".join(parts)

def make_random_attn_checks(source_lang: str, target_lang: str, checks_num: int, data_lang: dict) -> list[list[dict]]:
    models = set()
    for data_doc in data_lang.values():
        models.update(data_doc["tgt"].keys() & ATTENTION_CHECK_MODELS)
    if len(models) < 3:
        raise ValueError(f"Need at least three of {sorted(ATTENTION_CHECK_MODELS)} for {source_lang}->{target_lang}")

    candidates = []
    for data_doc in data_lang.values():
        doc_models = [m for m in data_doc["tgt"].keys() if m in ATTENTION_CHECK_MODELS]
        doc_candidates = []
        for bad_model in doc_models:
            clean_models = [m for m in doc_models if m != bad_model]
            for clean_model_a, clean_model_b in itertools.combinations(clean_models, 2):
                src_paragraphs = data_doc["src_text"]
                tgt_bad_paragraphs = data_doc["tgt"][bad_model]
                tgt_a_paragraphs = data_doc["tgt"][clean_model_a]
                tgt_b_paragraphs = data_doc["tgt"][clean_model_b]
                if not (len(src_paragraphs) == len(tgt_bad_paragraphs) == len(tgt_a_paragraphs) == len(tgt_b_paragraphs)):
                    continue

                #check the bad translation has enough words to shuffle
                parts = _tokenize(tgt_bad_paragraphs[0], target_lang)
                item_indexes = _eligible_indexes(parts)
                if len(item_indexes) <= _shuffle_count(target_lang) * 2:
                    continue

                doc_candidates.append(
                    (src_paragraphs[0], tgt_a_paragraphs[0], tgt_b_paragraphs[0], tgt_bad_paragraphs[0]))

        # keep only one combo per document, so checks_num draws from checks_num distinct documents
        if doc_candidates:
            candidates.append(random.choice(doc_candidates))

    if not candidates:
        raise ValueError(f"No matching documents found for {source_lang}->{target_lang}")
    if checks_num > len(candidates):
        raise ValueError(f"Asked for {checks_num} checks, but only {len(candidates)} unique candidates exist")

    examples = []

    random.shuffle(candidates)
    for src, tgt_a, tgt_b, tgt_bad in candidates[:checks_num]:
        tgt_bad = shuffle_words(tgt_bad, target_lang)

        labels = ["A", "B", "C"]
        random.shuffle(labels)
        clean_label_a, clean_label_b, bad_label = labels
        tgts = {clean_label_a: tgt_a, clean_label_b: tgt_b, bad_label: tgt_bad}
        # shuffle tgts
        tgts = {label: tgts[label] for label in random.sample(labels, len(labels))}
        tgt_label_to_i = {
            label: ["1st translation", "2nd translation", "3rd translation"][i]
            for i, label in enumerate(tgts.keys())
        }

        examples.append([{
            "src": src,
            "tgt": {tgt_label_to_i[label]: tgts[label] for label in tgts},
            "validation": {
                tgt_label_to_i[clean_label_a]: {
                    "warning": f"Please pay more attention. The {tgt_label_to_i[clean_label_a]} should be scored higher than the {tgt_label_to_i[bad_label]}.",
                    "score_greaterthan": tgt_label_to_i[bad_label],
                },
                tgt_label_to_i[clean_label_b]: {
                    "warning": f"Please pay more attention. The {tgt_label_to_i[clean_label_b]} should be scored higher than the {tgt_label_to_i[bad_label]}.",
                    "score_greaterthan": tgt_label_to_i[bad_label],
                },
            },
            "item_id": f"attention_check_{len(examples)}"
        }])

    return examples