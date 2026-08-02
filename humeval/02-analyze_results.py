# %%

import collections
import statistics
import scipy.stats
import typst
import json
import os
import numpy as np
import json
import utils
import os
import functools

os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")

with open("humeval/data/annotations.json", "r") as f:
    data = json.load(f)

# process __RESET__ actions and tutorial items
for langs, data_local in data.items():
    data_new = []
    for line in data_local:
        if line["annotation"] == "__RESET__":
            data_new = []
        elif "item_id" not in line["item"][0]:
            # attention check
            pass
        elif line["item"][0]["item_id"].startswith("attention_check_"):
            # attention check
            pass
        elif "_#_tutorial_#_" in line["item"][0]["item_id"]:
            # tutorial item
            pass
        else:
            data_new.append(line)
    data[langs] = data_new


os.makedirs("humeval/compiled/results_perlang/", exist_ok=True)
os.makedirs("humeval/compiled/results_progress/", exist_ok=True)

@functools.lru_cache(maxsize=None)
def is_significantly_better(
    scores_a: list[float | None],
    scores_b: list[float | None]
) -> bool:
    """Check if scores_a is significantly better than scores_b using a paired t-test."""
    _, p_value1 = scipy.stats.ttest_rel(scores_a, scores_b, nan_policy="omit")
    _, p_value2 = scipy.stats.ttest_ind(scores_a, scores_b, nan_policy="omit")

    return p_value1 < 0.05 or p_value2 < 0.05 # type: ignore

Model = str
Langs = str
Item = str
Doc = str

# kill all warnings
import warnings
warnings.filterwarnings("ignore")

with open("wmt26_participants.jsonl", "r") as f:
    participants = [json.loads(line) for line in f]
    participants_open = {
        x["System name (short, to be used in the overview paper)"]: x["Track"] == "Constrained open weights track (max 20B parameters; I will relase the model weights)"
        for x in participants
    }


data_global: dict[Model, dict[Langs, float]] = collections.defaultdict(lambda: collections.defaultdict(lambda: -100))

langs_i_printed = 0
for langs, data_local in data.items():
    if not data_local:
        continue

    data_model_item: dict[Model, dict[Item, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: []))
    item_ids = set()
    for line in data_local:
        for item_ann, item in zip(line["annotation"], line["item"]):
            item_ids.add(item["item_id"])
            for model, ann_obj in item_ann.items():
                model = model + (" OPEN" if participants_open.get(model, False) else "")
                data_model_item[model][item["item_id"]].append(ann_obj["score"])

    # sort by number of annotated models
    doc_ids = set()

    # ensure same order
    item_ids = list(item_ids)
    # average multiple annotations per item
    data_model_item_avg: dict[Model, list[float]] = {
        model: [
            (
                float(statistics.mean(data_model_item[model][item_id])) if item_id in data_model_item[model]
                else float("nan")
            )
            for item_id in item_ids
        ]
        for model in data_model_item
    }


    data_model_doc: dict[Model, dict[Doc, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: []))
    for model, item_scores in data_model_item_avg.items():
        for item_i, item_id in enumerate(item_ids):
            doc_id = item_id.rsplit("_###_", 1)[0]
            doc_ids.add(doc_id)
            if not np.isnan(item_scores[item_i]):
                data_model_doc[model][doc_id].append(item_scores[item_i])

    doc_ids = list(doc_ids)
    doc_ids.sort(key=lambda x: sum(1 for model in data_model_doc if x in data_model_doc[model]), reverse=True)
    

    data_models_flat = list(data_model_item_avg.items())
    # sort from top
    data_models_flat.sort(key=lambda x: statistics.mean([v for v in x[1] if not np.isnan(v)]), reverse=True)

    data_typst = []
    for model_i, (model, scores) in enumerate(data_models_flat):
        scores_nonan = [v for v in scores if not np.isnan(v)]
        scores_seg = [v if not np.isnan(v) else -100 for v in scores]
        scores_doc = [
            statistics.mean(data_model_doc[model][doc_id]) if doc_id in data_model_doc[model] else -100
            for doc_id in doc_ids
        ]
        # make it significant IFF it's beter than all subsequent models
        if model_i < len(data_models_flat) - 1:
            # check if we can make a cluster here

            significant_locally = is_significantly_better(
                tuple(data_models_flat[model_i][1]),
                tuple(data_models_flat[model_i + 1][1]),
            )
            # check that the current model is significantly better than all subsequent models
            significant_globally = (
                all(
                    is_significantly_better(
                        tuple(data_models_flat[model_up][1]),
                        tuple(data_models_flat[model_down][1]),
                    )
                    for model_up in range(0, model_i+1)
                    for model_down in range(model_i + 1, len(data_models_flat))
                )
            )

        data_typst.append({
            "model": model,
            "scores_seg": scores_seg,
            "scores_doc": scores_doc,
            "scores_mean": statistics.mean(scores_nonan),
            "cluster": (
                "nothing" if model_i == len(data_models_flat) - 1 else
                "yes_cluster" if significant_globally else # type: ignore
                "yes_local" if significant_locally # type: ignore
                else "nothing"
            )
        })

    langs = langs.removesuffix(" v3")
    lang1, lang2 = [utils.LANG_TO_NAME[lang] for lang in langs.split("---")]
    for model in data_model_item_avg:
        data_global[model][f"{lang1}---{lang2}"] = float(statistics.mean([v for v in data_model_item_avg[model] if not np.isnan(v)]))

    typst.compile(
        input="humeval/02-template-perlang.typ",
        sys_inputs={
            "data": json.dumps(data_typst),
            "langs": json.dumps(f"{lang1}---{lang2}")},
        output=f"humeval/compiled/results_perlang/{langs}.pdf"
    )
    typst.compile(
        input="humeval/02-template-progress.typ",
        sys_inputs={
            "data": json.dumps(data_typst),
            "langs": json.dumps(f"{lang1}---{lang2}")},
        output=f"humeval/compiled/results_progress/{langs}.pdf"
    )

    if langs_i_printed % 3 == 0:
        print("\n\\noindent")
    print(
        f"\\includegraphics[width=5cm]{{figures_new/results_perlang/{langs}.pdf}}",
        end=(r"\hfill" if langs_i_printed % 3 != 2 else "") + "\n"
    )

    langs_i_printed += 1

data_global_flat = list(data_global.items())
langs_all = list({lang for model in data_global for lang in data_global[model]})
# sort by average score across all languages
langs_all.sort(key=lambda x: statistics.mean([data_global[model][x] for model in data_global if data_global[model][x] != -100]), reverse=True)
data_global_flat = [
    [
        model,
        {lang: data_global[model][lang] for lang in langs_all}
    ]
    for model in data_global
]

# sort by average rank (not score), ignore -100 scores
model_average_rank = {
    model: statistics.mean(
        [
            sum(
                1 for other_model in data_global
                if data_global[other_model][lang] > data_global[model][lang]
            ) / len([
                other_model for other_model in data_global
                if data_global[other_model][lang] != -100
            ])
            for lang in langs_all
            if data_global[model][lang] != -100
        ]
    )
    for model in data_global
}
data_global_flat.sort(key=lambda x: model_average_rank[x[0]])

typst.compile(
    input="humeval/02-template-global.typ",
    sys_inputs={
        "data": json.dumps(data_global_flat),
    },
    output=f"humeval/compiled/results_global.pdf"
)