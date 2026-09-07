import collections
import itertools
import statistics
import math
import json
import os
import csv

os.chdir(os.path.dirname(__file__) + "/..")
os.makedirs("humeval/compiled/", exist_ok=True)

with open("humeval/data/annotations_filtered.json", "r") as f:
    data_filtered = json.load(f)


IDLE_CAP_SECONDS = 60

def line_duration(line):
    times = sorted(a["time"] for a in line.get("actions", []))
    if len(times) < 2:
        return None
    return sum(min(t2 - t1, IDLE_CAP_SECONDS) for t1, t2 in zip(times, times[1:]))


rows = []
for langs, data_lang in data_filtered.items():
    if not data_lang:
        continue

    n_annotations = 0
    n_minor = 0
    n_major = 0
    systems = set()
    users = set()
    # (item_id, model) -> {user_id: score}, to find items scored by >1 annotator
    dup_groups = collections.defaultdict(dict)
    total_time = 0.0
    total_time_items = 0

    for line in data_lang:
        user = line["user_id"]
        users.add(user)
        for item, item_ann in zip(line["item"], line["annotation"]):
            item_id = item["item_id"]
            for model, ann_obj in item_ann.items():
                systems.add(model)
                n_annotations += 1
                for span in ann_obj["error_spans"]:
                    if span["severity"] == "minor":
                        n_minor += 1
                    elif span["severity"] == "major":
                        n_major += 1
                dup_groups[(item_id, model)][user] = ann_obj["score"]

        dur = line_duration(line)
        if dur is not None:
            total_time += dur
            total_time_items += sum(len(item_ann) for item_ann in line["annotation"])

    # MAE between duplicate annotations
    abs_diffs = []
    for scores_by_user in dup_groups.values():
        scores = list(scores_by_user.values())
        if len(scores) >= 2:
            abs_diffs.extend(abs(s1 - s2) for s1, s2 in itertools.combinations(scores, 2))

    rows.append({
        "langs": langs.removesuffix(" v3"),
        "n_annotations": n_annotations,
        "n_systems": len(systems),
        "avg_per_system": n_annotations / len(systems) if systems else float("nan"),
        "avg_minor": n_minor / n_annotations if n_annotations else float("nan"),
        "avg_major": n_major / n_annotations if n_annotations else float("nan"),
        "n_annotators": len(users),
        "mae": statistics.mean(abs_diffs) if abs_diffs else float("nan"),
        "avg_time_per_seg": total_time / total_time_items if total_time_items else float("nan"),
    })

# matches the row order of the table in the paper 
LANG_PAIR_ORDER = [
    "eng_Latn---zho_Hans",
    "eng_Latn---zho_Hant_TW",
    "eng_Latn---jpn_Jpan",
    "eng_Latn---kor_Hang",
    "eng_Latn---hye_Armn",
    "eng_Latn---kaz_Cyrl",
    "eng_Latn---bel_Cyrl",
    "zho_Hans---jpn_Jpan",
    "eng_Latn---lld_Latn",
    "eng_Latn---ekk_Latn",
    "eng_Latn---sme_Latn",
    "ces_Latn---vie_Latn",
    "ces_Latn---deu_Latn",
    "eng_Latn---ces_Latn",
    "eng_Latn---ukr_Cyrl",
    "eng_Latn---arz_Arab",
    "eng_Latn---rus_Cyrl",
    "eng_Latn---isl_Latn",
    "eng_Latn---deu_Latn",
    "ces_Latn---ukr_Cyrl",
    "eng_Latn---tha_Thai",
    "eng_Latn---ind_Latn",
    "eng_Latn---lij_Latn",
]
rows.sort(key=lambda r: LANG_PAIR_ORDER.index(r["langs"]) if r["langs"] in LANG_PAIR_ORDER else len(LANG_PAIR_ORDER))


def fmt(v, spec=""):
    if isinstance(v, float) and math.isnan(v):
        return "n/a"
    return format(v, spec)


headers = ["Lang pair", "# annot.", "# sys.", "avg/sys", "minor/item", "major/item", "# annot.", "MAE(dup)", "time/seg(s)"]
col_widths = [24, 9, 7, 8, 11, 11, 9, 9, 11]


def fmt_row(vals):
    return " | ".join(str(v).rjust(w) for v, w in zip(vals, col_widths))


print(fmt_row(headers))
print("-" * (sum(col_widths) + 3 * (len(col_widths) - 1)))
for r in rows:
    print(fmt_row([
        r["langs"],
        r["n_annotations"],
        r["n_systems"],
        fmt(r["avg_per_system"], ".1f"),
        fmt(r["avg_minor"], ".2f"),
        fmt(r["avg_major"], ".2f"),
        r["n_annotators"],
        fmt(r["mae"], ".2f"),
        fmt(r["avg_time_per_seg"], ".1f"),
    ]))

with open("humeval/compiled/annotations_table.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "lang_pair", "n_annotations", "n_systems", "avg_annotations_per_system",
        "avg_minor_errors_per_item", "avg_major_errors_per_item", "n_annotators",
        "mae_duplicate_annotations", "avg_time_per_segment_seconds",
    ])
    for r in rows:
        writer.writerow([
            r["langs"], r["n_annotations"], r["n_systems"],
            round(r["avg_per_system"], 3) if not math.isnan(r["avg_per_system"]) else "",
            round(r["avg_minor"], 1) if not math.isnan(r["avg_minor"]) else "",
            round(r["avg_major"], 1) if not math.isnan(r["avg_major"]) else "",
            r["n_annotators"],
            round(r["mae"], 2) if not math.isnan(r["mae"]) else "",
            round(r["avg_time_per_seg"], 1) if not math.isnan(r["avg_time_per_seg"]) else "",
        ])

print("\nSaved: humeval/compiled/annotations_table.csv")
