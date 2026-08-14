# %%

import collections
import itertools
import statistics
import json
import os
import json
import os
import matplotlib.pyplot as plt

os.chdir(os.path.dirname(__file__) + "/..")

with open("humeval/data/annotations.json", "r") as f:
    data = json.load(f)

# process __RESET__ actions and tutorial items
for langs, data_local in data.items():
    data_new_user = collections.defaultdict(list)
    for line in data_local:
        if line["annotation"] == "__RESET__":
            data_new_user[line["user_id"]] = []
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
            data_new_user[line["user_id"]].append(line)
    data[langs] = [line for user_lines in data_new_user.values() for line in user_lines]

logprobs = []

def filter_data_lang(langs, data_lang):
    if not data_lang:
        return data_lang
    data_by_user = collections.defaultdict(list)
    for line in data_lang:
        data_by_user[line["user_id"]].append(line)

    user_banlist = set()
    for user, data_user in data_by_user.items():
        # don't discard users with less than 3 items
        if len(data_user) < 3:
            continue
        model_scores_without_user = collections.defaultdict(list)
        model_scores_with_user = collections.defaultdict(list)
        for line in data_lang:
            for item_ann, item in zip(line["annotation"], line["item"]):
                for model, ann_obj in item_ann.items():
                    model_scores_without_user[model].append(ann_obj["score"])

        model_scores_pairwise_mu = {
            (model1, model2): statistics.mean(scores1) - statistics.mean(scores2)
            for model1, scores1 in model_scores_without_user.items()
            for model2, scores2 in model_scores_without_user.items()
            if model1 != model2 and len(scores1) > 10 and len(scores2) > 10
        }
        model_scores_pairwise_var = {
            (model1, model2): statistics.variance(scores1) + statistics.variance(scores2)
            for model1, scores1 in model_scores_without_user.items()
            for model2, scores2 in model_scores_without_user.items()
            if model1 != model2 and len(scores1) > 10 and len(scores2) > 10
        }
        user_probs = []
        for line in data_user:
            for item_ann, item in zip(line["annotation"], line["item"]):
                for (model1, ann_obj1), (model2, ann_obj2) in itertools.combinations(item_ann.items(), 2):
                    if (model1, model2) not in model_scores_pairwise_var:
                        continue
                    logprob = -(
                        (ann_obj1["score"] - ann_obj2["score"] - model_scores_pairwise_mu[(model1, model2)]) ** 2
                        / (2 * model_scores_pairwise_var[(model1, model2)] + 1e-6)
                    )
                    user_probs.append(2**logprob)

        if user_probs:
            prob = statistics.mean(user_probs)
            print(f"{langs} {user:>35} {prob:.2f} prob for {len(data_user)} items")
            logprobs.append(prob)
            if prob < 0.75:
                user_banlist.add(user)

    print("Removing users with low annotation prob:", len(user_banlist), langs)
    return [line for line in data_lang if line["user_id"] not in user_banlist]

data = {langs: filter_data_lang(langs, data_lang) for langs, data_lang in data.items()}

plt.hist(logprobs, bins=40, color="black")
plt.xlim(0.5, 1)
plt.gca().spines[['top', 'right']].set_visible(False)
plt.ylabel("Number of users")
plt.xlabel("Probablity")
plt.show()

with open("humeval/data/annotations_filtered.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)