# %%

import collections
import random
import statistics
import scipy.stats
import typst
import json
import os
import numpy as np
import json
import utils
import os
import math
import functools
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "serif"
 
os.chdir(os.path.dirname(__file__) + "/..")

with open("humeval/data/annotations_filtered.json", "r") as f:
    data = json.load(f)

os.makedirs("humeval/compiled/results_perlang/", exist_ok=True)

@functools.lru_cache(maxsize=None)
def is_significantly_better_parametric(
    scores_a: tuple[float | None, ...],
    scores_b: tuple[float | None, ...]
) -> bool:
    try:
        _, p_value1 = scipy.stats.wilcoxon(scores_a, scores_b, nan_policy="omit", alternative="greater") # type: ignore
    except ValueError:
        p_value1 = 1.0

    try:
        _, p_value2 = scipy.stats.ttest_ind(scores_a, scores_b, nan_policy="omit", alternative="greater")
    except ValueError:
        p_value2 = 1.0

    return p_value1 < 0.05 or p_value2 < 0.05 # type: ignore

@functools.lru_cache(maxsize=None)
def is_significantly_better(
    scores_a: tuple[float | None, ...],
    scores_b: tuple[float | None, ...],
    n_resamples: int = 100
) -> bool:
    pairs = [
        (a, b) for a, b in zip(scores_a, scores_b)
        if a is not None and b is not None and not math.isnan(a) and not math.isnan(b)
    ]
    diffs = np.array([a - b for a, b in pairs])
    
    valid_a = np.array([a for a in scores_a if a is not None and not math.isnan(a)])
    valid_b = np.array([b for b in scores_b if b is not None and not math.isnan(b)])

    if len(diffs) >= 2 and np.any(diffs > 0):
        try:
            res_paired = scipy.stats.bootstrap(
                (diffs,),
                statistic=np.mean,
                vectorized=True,
                n_resamples=n_resamples,
                confidence_level=0.95, 
                alternative="greater"
            )
            if res_paired.confidence_interval.low > 0:
                return True
        except ValueError:
            pass

    if len(valid_a) >= 2 and len(valid_b) >= 2:
        def ind_mean_diff(x, y, axis=-1):
            return np.mean(x, axis=axis) - np.mean(y, axis=axis)
            
        try:
            res_ind = scipy.stats.bootstrap(
                (valid_a, valid_b),
                statistic=ind_mean_diff,
                vectorized=True,
                n_resamples=n_resamples,
                confidence_level=0.95,
                alternative="greater"
            )
            if res_ind.confidence_interval.low > 0:
                return True
        except ValueError:
            pass

    return False


@functools.lru_cache(maxsize=None)
def confidence_interval(
    scores: list[float],
    confidence: float = 0.95,
) -> tuple[float, float]:
    # t-test for numpy scipy
    # drop none and nan
    data = np.array(scores)
    data = data[~np.isnan(data)]
    return scipy.stats.t.interval(
        confidence=confidence,
        df=len(data)-1,
        loc=np.mean(data),
        scale=scipy.stats.sem(data)
    )

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


MODEL_OVERRIDES = {
    "Grial-SalamandraTA7bFFT": {"open_lookup": "SalamandraTA7bFFT"},
    "VoxNexus_V1": {"display": "[Anonymous]"},
}


data_global: dict[Model, dict[Langs, float]] = collections.defaultdict(lambda: collections.defaultdict(lambda: -100))
data_for_perlang = []
data_global_domains = []
all_scores_global = []
top_system_scores_global = []
top_translation_scores_global = []

langs_i_printed = 0
significance_counter = collections.defaultdict(list)
for langs, data_local in data.items():
    if not data_local:
        continue

    langs = langs.removesuffix(" v3")
    lang1, lang2 = [utils.LANG_TO_NAME[lang] for lang in langs.split("---")]

    data_model_item: dict[Model, dict[Item, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: []))
    item_ids = set()
    for line in data_local:
        for item_ann, item in zip(line["annotation"], line["item"]):
            item_ids.add(item["item_id"])
            for model, ann_obj in item_ann.items():
                overrides = MODEL_OVERRIDES.get(model, {})
                is_open = participants_open.get(overrides.get("open_lookup", model), False)
                model = overrides.get("display", model.replace("7bFFT", "")) + (" OPEN" if is_open else "")
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

    for model in data_model_item_avg:
        data_global[model][f"{lang1}---{lang2}"] = float(statistics.mean([v for v in data_model_item_avg[model] if not np.isnan(v)]))


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

    top_model = data_models_flat[0][0]

    # Excluding Human systems from results_global_domains.pdf
    data_models_flat_no_human = [x for x in data_models_flat if not x[0].startswith("Human (")]

    # macro-average across systems
    domain_scores_per_model = collections.defaultdict(list)
    for model, item_scores in data_models_flat_no_human:
        per_model_domain_scores = collections.defaultdict(list)
        for i, item_id in enumerate(item_ids):
            domain = item_id.split("_###_", 1)[0]
            score = item_scores[i]
            if not np.isnan(score):
                per_model_domain_scores[domain.capitalize()].append(score)
        for domain, scores in per_model_domain_scores.items():
            domain_scores_per_model[domain].append(statistics.mean(scores))
    row_domains = {d: statistics.mean(s) for d, s in domain_scores_per_model.items()}
    # macro-average across domains, excluding Factchecking/Edu
    row_domains["Avg."] = statistics.mean([v for d, v in row_domains.items() if d not in ("Factchecking", "Edu")])
    data_global_domains.append([f"{lang1}---{lang2}", row_domains])

    for model_scores in data_model_item_avg.values():
        all_scores_global.extend([s for s in model_scores if not np.isnan(s)])
    
    top_system_scores_global.extend([s for s in data_model_item_avg[top_model] if not np.isnan(s)])

    for i in range(len(item_ids)):
        item_scores = [data_model_item_avg[model][i] for model in data_model_item_avg if not np.isnan(data_model_item_avg[model][i])]
        if item_scores:
            top_translation_scores_global.append(max(item_scores))


    # print for Findings paper
    if langs_i_printed % 3 == 0:
        print("\n\\noindent")
    print(
        f"\\includegraphics[width=5cm]{{figures/results_perlang/{langs}.pdf}}",
        end=(r"\hfill" if langs_i_printed % 3 != 2 else "") + "\n"
    )

    langs_i_printed += 1

    # store for later
    data_model_doc = {model: dict(docs) for model, docs in data_model_doc.items()} # type: ignore
    data_for_perlang.append((lang1, lang2, data_models_flat, data_model_doc, doc_ids))


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

        # find the rank of the first model that is not significantly better than the current model
        rank_top = model_i
        for rank_top in range(model_i, 0-1, -1):
            if is_significantly_better(
                tuple(data_models_flat[rank_top-1][1]),
                tuple(data_models_flat[model_i][1]),
            ):
                break

        rank_bottom = model_i
        # find the rank of the last model that is not significantly worse than the current model
        for rank_bottom in range(model_i, len(data_models_flat)-1):
            if is_significantly_better(
                tuple(data_models_flat[model_i][1]),
                tuple(data_models_flat[rank_bottom+1][1]),
            ):
                break

        if model_i != len(data_models_flat) - 1:
            significance_counter["local"].append(int(significant_locally)) # type: ignore
            significance_counter["global"].append(int(significant_globally)) # type: ignore

        data_typst.append({
            "model": model,
            "scores_seg": scores_seg,
            "scores_doc": scores_doc,
            "scores_mean": statistics.mean(scores_nonan),
            "rank_top": rank_top + 1,
            "rank_bottom": rank_bottom + 1,
            "cluster": (
                "nothing" if model_i == len(data_models_flat) - 1 else
                "yes_cluster" if significant_globally else # type: ignore
                "yes_local" if significant_locally # type: ignore
                else "nothing"
            )
        })

    typst.compile(
        input="humeval/02-template-perlang.typ",
        sys_inputs={
            "data": json.dumps(data_typst),
            "langs": json.dumps(f"{lang1}---{lang2}")},
        output=f"humeval/compiled/results_perlang/{langs}.pdf"
    )

    if langs == "ces_Latn---deu_Latn":
        typst.compile(
            input="humeval/02-template-progress.typ",
            sys_inputs={
                "data": json.dumps(data_typst),
                "langs": json.dumps(f"{lang1}---{lang2}")},
            output=f"humeval/compiled/dynamic_assignment_checkboxes.pdf"
        )

        # plot nice dynamic figure for the paper
        plt.figure(figsize=(4, 2.5))
        # select only few models for clarity
        data_models_flat_filtered = data_models_flat[::2]
        # for each model show how confidence intervals evolve as we add more evaluations points
        for model, scores in data_models_flat_filtered:
            # stable shuffle
            scores = random.Random(0).sample(scores, len(scores))
            intervals = [
                confidence_interval(tuple(scores[:chunk_i]), confidence=0.5)
                for chunk_i in range(len(scores))
            ]
            xs = range(len(scores))

            # select only scores that are not nan
            xs_active, ys_active = zip(*[
                (x, (low + high) / 2)
                for x, (low, high), y in zip(xs, intervals, scores)
                if not math.isnan(y)
            ])
            plt.scatter(
                xs_active,
                ys_active,
                color="black",
                s=0.5,
                linewidth=0,
            )
            plt.fill_between(
                xs,
                [low for low, high in intervals],
                [high for low, high in intervals],
                alpha=0.2,
                # color="black",
                linewidth=0,
            )
        plt.gca().spines[['top', 'right']].set_visible(False)
        plt.ylim(40, 90)
        plt.ylabel("Rolling model average")
        plt.xlim(5, None)
        plt.xlabel("Annotations")
        plt.tight_layout(pad=0.1)
        plt.savefig("humeval/compiled/dynamic_assignment_intervals.pdf", bbox_inches='tight')

print()
print(f"local  {statistics.mean(significance_counter['local']):.2f}, {sum(significance_counter['local'])}")
print(f"global {statistics.mean(significance_counter['global']):.2f}, {sum(significance_counter['global'])}")

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

all_domains_set = {}
for row in data_global_domains:
    for d in row[1].keys():
        if d != "Avg." and d not in ("Factchecking", "Edu"):
            all_domains_set[d] = None

domain_avg = {}
for d in all_domains_set.keys():
    scores = [row[1][d] for row in data_global_domains if d in row[1] and row[1][d] != -100]
    domain_avg[d] = statistics.mean(scores) if scores else -100

sorted_domains = sorted(all_domains_set.keys(), key=lambda d: domain_avg[d], reverse=True)
all_domains = sorted_domains + ["Avg."]

data_global_domains.sort(key=lambda row: row[1].get("Avg.", -100), reverse=True)

for row in data_global_domains:
    row[1] = {d: row[1].get(d, -100) for d in all_domains}

typst.compile(
    input="humeval/02-template-global_domains.typ",
    sys_inputs={
        "data": json.dumps(data_global_domains),
    },
    output=f"humeval/compiled/results_global_domains.pdf"
)

# %%

fig, ax = plt.subplots(figsize=(4, 2.5))
colors = ['#cbaf5d', '#5d9acb', '#79cb5d']
labels = ['All', 'Top system', 'Top translation']

data_to_plot = [all_scores_global, top_system_scores_global, top_translation_scores_global]
weights = [np.ones(len(x)) / len(x) if len(x) > 0 else [] for x in data_to_plot]

ax.hist(
    data_to_plot,
    bins=20,
    range=(0, 100),
    color=colors,
    label=labels,
    weights=weights,
    edgecolor='none'
)

ax.set_xlabel('cESA Score', fontsize=12)
ax.set_ylabel('Frequency', fontsize=12)
# shift xticks to the left
ax.set_xticks(
    np.arange(0, 101, 10)-2.5,
    np.arange(0, 101, 10)
)
ax.set_yticks([])

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_visible(True)
ax.spines['bottom'].set_visible(True)

ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=3, frameon=False, handletextpad=0.2, columnspacing=1)

plt.tight_layout(pad=0)
plt.savefig('humeval/compiled/results_segment_headroom.pdf', bbox_inches='tight')