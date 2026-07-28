# %%

import json

with open("data/annotations.json", "r") as f:
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

# %%

import collections
import statistics
import scipy.stats
import typst
import json
import os
import numpy as np
import utils

os.makedirs("compiled", exist_ok=True)

Model = str
Langs = str
Item = str

data_global: dict[Model, dict[Langs, float]] = collections.defaultdict(lambda: collections.defaultdict(lambda: -100))

for langs, data_local in data.items():
    if not data_local:
        continue

    data_model_item: dict[Model, dict[Item, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: []))
    item_ids = set()
    for line in data_local:
        for item_ann, item in zip(line["annotation"], line["item"]):
            item_ids.add(item["item_id"])
            for model, ann_obj in item_ann.items():
                data_model_item[model][item["item_id"]].append(ann_obj["score"])

    # ensure same order
    item_ids = list(item_ids)
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

    data_models_flat = list(data_model_item_avg.items())
    # sort from top
    data_models_flat.sort(key=lambda x: statistics.mean([v for v in x[1] if not np.isnan(v)]), reverse=True)

    data_typst = []
    for model_i, (model, scores) in enumerate(data_models_flat):
        scores_clean = [v for v in scores if not np.isnan(v)]
        if model_i < len(data_models_flat) - 1:
            # t-test against next model
            _, p_value = scipy.stats.ttest_rel(
                data_models_flat[model_i][1],
                data_models_flat[model_i+1][1],
                nan_policy="omit",
            )
            significant = p_value < 0.05 # type: ignore
        else:
            significant = False
        data_typst.append([model, statistics.mean(scores_clean), "yes" if significant else "no"])

    langs = langs.removesuffix(" v3")
    lang1, lang2 = [utils.LANG_TO_NAME[lang] for lang in langs.split("---")]
    for model in data_model_item_avg:
        data_global[model][f"{lang1}---{lang2}"] = float(statistics.mean([v for v in data_model_item_avg[model] if not np.isnan(v)]))

    print(lang1, lang2)
    typst.compile(
        input="02-template-perlang.typ",
        sys_inputs={
            "data": json.dumps(data_typst),
            "langs": json.dumps([lang1, lang2])},
        output=f"compiled/results_{langs}.pdf"
    )

data_global_flat = list(data_global.items())
langs_all = list({lang for model in data_global for lang in data_global[model]})
# sort by average score across all languages
langs_all.sort(key=lambda x: statistics.mean([data_global[model][x] if data_global[model][x] != -100 else -100000 for model in data_global]), reverse=True)
data_global_flat = [
    [model, {lang: data_global[model][lang] for lang in langs_all}]
    for model in data_global
]

# sort by average rank (not score), ignore -100 scores
model_average_rank = {
    model: statistics.mean(
        [
            sum(
                1 for other_model in data_global
                if data_global[other_model][lang] > data_global[model][lang]
            )
            for lang in langs_all
            if data_global[model][lang] != -100
        ]
    )
    for model in data_global
}
data_global_flat.sort(key=lambda x: model_average_rank[x[0]])

typst.compile(
    input="02-template-global.typ",
    sys_inputs={
        "data": json.dumps(data_global_flat),
    },
    output=f"compiled/results_global.pdf"
)