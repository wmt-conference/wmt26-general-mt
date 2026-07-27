# %%

"""
# get a local copy of the data
git clone git@github.com:wmt-conference/wmt26-generalmt-internal.git --depth 1 --branch main2
"""

"""
# create mock "human" submission
cat wmt26-generalmt-internal/references/aligned/refPE/*/*.jsonl > "wmt26-generalmt-internal/submissions/aligned/Human (postediting).jsonl"
cat wmt26-generalmt-internal/references/aligned/refA/*/*.jsonl > "wmt26-generalmt-internal/submissions/aligned/Human (from scratch).jsonl"
"""

import pearmut.constants # type: ignore
INSTRUCTIONS_DOMAIN = {
    "news": "Ensure the translation is formal and consistent with journalistic standards",
    "factchecking": "Ensure the translation is formal and consistent with journalistic standards.",
    "speech": "Check the translation maintains the flow and colloquial style of the speaker. Translation should not include non-linguistic sounds (e.g. laughter, groans, hesitation sounds, etc.), but should include interjections. If a word is interrupted, translations should either guess the full word if possible or otherwise omit it. Foreign words should be preserved.",
    "social": "Spelling mistakes should not be reproduced. Marks of expressiveness that communicate meaningful intent (e.g. enthusiasm through capitalisation or elongation) in a way that is natural should be reproduced in the translation. URLs and user handles should be copied directly rather than being translated. Hashtags should be translated as appropriate for the translation to be natural for social media text. Punctuation of the source text should be followed as best as possible. Translation should be in an informal style, like close friends talking, even if it changes the original tone.",
    "software": 'Translation should translate the content of the JSON, without translating keys (such as "general.duration.years") and placeholders (e. g. "{{count}}").',
    "edu": "Translation should be accurate and maintain the instructional nature of the content. Ensure that technical terms are translated correctly and consistently."
}


import glob
import random
import collections
from typing import TypedDict, Optional
import json
from attention_checks import make_random_attn_checks
import os
os.chdir(os.path.dirname(__file__)+ "/..")
os.makedirs("campaigns", exist_ok=True)

LANG_TO_TUTORIAL = {
    "ces_Latn---deu_Latn": "csen", # deen for cs->de
    "ces_Latn---ukr_Cyrl": "uken", # uken for cs->uk
    "ces_Latn---vie_Latn": "csen", # csen for cs->vi
    "eng_Latn---ukr_Cyrl": "uken",
    "zho_Hans---jpn_Jpan": "zhen", # zhen for zh->ja
    "eng_Latn---hye_Armn": "hyen",
    "eng_Latn---bel_Cyrl": "been",
    "eng_Latn---kaz_Cyrl": "kken",
    "eng_Latn---rus_Cyrl": "ruen",
    "eng_Latn---arz_Arab": "aren",
    "eng_Latn---zho_Hans": "zhen",
    "eng_Latn---zho_Hant": "zhTWen",
    "eng_Latn---zho_Hant_TW": "zhTWen",
    "eng_Latn---ces_Latn": "csen",
    "eng_Latn---ekk_Latn": "eten",
    "eng_Latn---deu_Latn": "deen",
    "eng_Latn---isl_Latn": "isen",
    "eng_Latn---ind_Latn": "iden",
    "eng_Latn---jpn_Jpan": "jaen",
    "eng_Latn---kor_Hang": "koen",
    "eng_Latn---lij_Latn": "iten", # iten for en->Ligurian
    "eng_Latn---lld_Latn": "iten", # iten for en->Ladin
    "eng_Latn---sme_Latn": "seen",
    "eng_Latn---tha_Thai": "then",
}

LANG_TO_NAME = {
    "eng_Latn": "English",
    "ces_Latn": "Czech",
    "deu_Latn": "German",
    "ukr_Cyrl": "Ukrainian",
    "vie_Latn": "Vietnamese",
    "jpn_Jpan": "Japanese",
    "hye_Armn": "Armenian",
    "bel_Cyrl": "Belarusian",
    "kaz_Cyrl": "Kazakh",
    "rus_Cyrl": "Russian",
    "arz_Arab": "Egyptian Arabic",
    "zho_Hans": "Simplified Chinese",
    "zho_Hant": "Traditional Chinese",
    "zho_Hant_TW": "Traditional Chinese",
    "ekk_Latn": "Estonian",
    "isl_Latn": "Icelandic",
    "ind_Latn": "Indonesian",
    "kor_Hang": "Korean",
    "lij_Latn": "Ladin",
    "lld_Latn": "Ligurian",
    "sme_Latn": "Northern Sami",
    "tha_Thai": "Thai",
}

# index by 
LanguagePair = tuple[str, str]
DocId = str
Model = str
class DocumentDict(TypedDict):
    src: list[str]
    src_text: list[str]
    tgt: dict[Model, list[str]]
    domain: str
    multimodal_path: Optional[str]

data_all: dict[LanguagePair, dict[DocId, DocumentDict]] = collections.defaultdict(dict)

# load sources from blindset/internal
with open("wmt26-generalmt-internal/blindset/internal_segmented.jsonl", "r") as f:
    data_blindset_internal = [json.loads(line) for line in f]
for line in data_blindset_internal:
    if not line["doc_id"].startswith("WMT26_###_"):
        continue
    line["doc_id"] = line["doc_id"].removeprefix("WMT26_###_")
    domain, lang1, lang2, doc_id = line["doc_id"].split("_###_")

    src = list(line["source_doc_segmented"])
    src_text = list(line["source_doc_segmented"])
    if line["multimodal_input_path"] is None:
        pass
    elif line["multimodal_input_path"].endswith(".mp4"):
        assert len(src) == 1, f"Video document {line['doc_id']} should have only one segment, but has {len(src)} segments"
        src = ["<video src='assets/" + line["multimodal_input_path"] + "' controls></video>"]
    elif os.path.isdir("wmt26-generalmt-internal/blindset/" + line["multimodal_input_path"]):
        img_name = line["multimodal_input_path"].split("/")[-1]
        fdir = f"wmt26-generalmt-internal/blindset/{line['multimodal_input_path']}"
        files_i = [x.split("_")[-1].removesuffix("-anon.png") for x in os.listdir(fdir) if not x.endswith("-all-anon.png")]
        files_i.sort()
        if len(files_i) != len(src):
            print(f"Image document {doc_id} ({img_name}) should have {len(src)} images, but has {len(files_i)} images")
            # keeping src and src_text
        else:
            for i, img_i in enumerate(files_i):
                fname = f"wmt26-generalmt-internal/blindset/multimodal_inputs/{img_name}/{img_name}_{img_i}-anon.png"
                assert os.path.isfile(fname), f"Image file {fname} does not exist"
                src[i] = "<img src='assets/" + line["multimodal_input_path"] + f"/{img_name}_{img_i}-anon.png' />"
    else:
        raise ValueError(f"Unknown multimodal input path: {line['multimodal_input_path']}")

    data_all[(lang1, lang2)][domain + "_###_" + doc_id] = DocumentDict(
        src=src,
        src_text=src_text,
        tgt={},
        domain=domain,
        multimodal_path=line["multimodal_input_path"]
    )

for file in glob.glob("wmt26-generalmt-internal/submissions/aligned/*.jsonl"):
    model = file.split("/")[-1].removesuffix(".jsonl")
    with open(file, "r") as f:
        data_model = [json.loads(line) for line in f]

    for line in data_model:
        doc_id = line["internal_doc_id"].removeprefix("WMT26_###_")
        domain, lang1, lang2, doc_id = doc_id.split("_###_")

        # hotfix for naming
        if "hypothesis_segmented" not in line and "segmented_refA" in line:
            line["hypothesis_segmented"] = line["segmented_refA"]
        if "hypothesis_segmented" not in line and "segmented_refPE" in line:
            line["hypothesis_segmented"] = line["segmented_refPE"]
        
        if all(len(x.strip().replace("<p>", "").replace("</p>", "")) == 0 for x in line["hypothesis_segmented"]):
            print(f"Warning: {model} has an empty segment translation for {lang1} {lang2} {domain} {doc_id}")
        hypothesis_segmented = [
            x.removesuffix("\n") + " " if x.endswith("\n") else x
            for x in line["hypothesis_segmented"]
        ]
        if domain + "_###_" + doc_id not in data_all[(lang1, lang2)]:
            print(f"Warning: source document {lang1} {lang2} {doc_id} not found, skipping")
            continue
        data_all[(lang1, lang2)][domain + "_###_" + doc_id]["tgt"][model] = hypothesis_segmented

# various checks of integrity
for (lang1, lang2), data_lang in data_all.items():
    # number of models
    first_doc_models = set(next(iter(data_lang.values()))["tgt"])
    print(lang1, lang2, len(first_doc_models))
    assert all(len(data_doc["tgt"]) == len(first_doc_models) for data_doc in data_lang.values())

    # segment count
    for doc_id, data_doc in data_lang.items():
        if not all(len(data_doc["tgt"][model]) == len(data_doc["src"]) for model in data_doc["tgt"]):
            print(f"ALERT: Segment count mismatch for {lang1}---{lang2} {doc_id}")
            print([len(data_doc["tgt"][model]) for model in data_doc["tgt"]])
            continue

# %%

# help me find coldstart items

items_coldstart = collections.defaultdict(lambda: collections.defaultdict(set))
for (lang1, lang2), data_lang in data_all.items():
    for doc_id, data_doc in data_lang.items():
        items_coldstart[lang1][data_doc["domain"]].add((doc_id, len(data_doc["src"])))

for lang1, domain_dict in items_coldstart.items():
    for domain, items in domain_dict.items():
        # sort from shortest
        items = list(items)
        items.sort(key=lambda x: x[1], reverse=False)
        print(lang1, domain)
        for doc_id, seg_count in items[:200]:
            print(f"    \"{doc_id}\", # ({seg_count})")


# %%

# our instructions
_LINE_LOCATION = '<li><strong>Missing text:</strong> Select the <code style="font-family: monospace">[MISSING]</code> tag if the translation omits important source text.</li>'
_LINE_NEW = '<li><strong>Instruction fault:</strong> If the translation does not follow the specialized evaluation instructions, mark it with the <code style="font-family: monospace">[instructions fault]</code> tag.</li>'
PROTOCOL_INSTRUCTIONS = pearmut.constants.PROTOCOL_INSTRUCTIONS["cESA"].split(_LINE_LOCATION)[0] + _LINE_LOCATION + _LINE_NEW + pearmut.constants.PROTOCOL_INSTRUCTIONS["cESA"].split(_LINE_LOCATION)[1]

COLDSTART_PRIORITY =  {
"eng_Latn": [
    # English source (62 items, 20 docs)
    # 14 items
    "social_###_116316727640084135", # (3)
    "social_###_116272918492881244", # (3)
    "social_###_116262294091035303", # (3)
    "social_###_116319514177552286", # (5)
    # 20 items
    "software_###_2-in-app-strings-products", # (20)
    # 15 items
    "news_###_brisbanetimes.com.au.377415", # (11)
    "news_###_newrepublic.com.18633", # (4)
    # 13 items
    "speech_###_id_GcvbtvPQP9w_512.61-536.73", # (1)
    "speech_###_id_vAG7mQyDIm8_11.06-33.34", # (1)
    "speech_###_id_oE5aAhhg7IY_314.94-344.54", # (1)
    "speech_###_id_o5rhwYz5-6g_304.42-326.06", # (1)
    "speech_###_id_1DJUl6tjPQE_449.81-471.69", # (1)
    "speech_###_id_XrwolWfzuoQ_125.78-155.82", # (1)
    "speech_###_id_pdUl_VIXkJk_27.78-53.71", # (1)
    "speech_###_id_c5h2yMQvcMM_202.62-227.94", # (1)
    "speech_###_id_URDI_PdMfDE_167.62-190.18", # (1)
    "speech_###_id_iKPehn7Os00_287.58-312.34", # (1)
    "speech_###_id_1DJUl6tjPQE_36.54-65.38", # (1)
    "speech_###_id_RJUgPw-C8Tk_424.49-448.77", # (1)
    "speech_###_id_TELSYv3zYz4_457.25-487.45", # (1)
],

"ces_Latn": [
    # Czech source (49 items, 20 docs)
    # 9 items
    "social_###_116318953167896778", # (3)
    "social_###_116346783912326469", # (3)
    "social_###_116334388757462546", # (3)
    # 10 items
    "news_###_radio_praha-cs.23924", # (2)
    "news_###_ihned.cz.70745", # (4)
    "news_###_aha-cs.39129", # (4)
    # 10 items
    "speech_###_id_bATeFEZfADA_565.13-588.12", # (1)
    "speech_###_id_qiVm9PrsyIo_530.65-553.59", # (1)
    "speech_###_id_uAP0lctmQDc_345.02-367.11", # (1)
    "speech_###_id_snzv25RTDCA_79.94-106.23", # (1)
    "speech_###_id_SEY8kagezBQ_468.54-499.89", # (1)
    "speech_###_id_pwD35UnvKY4_369.53-394.77", # (1)
    "speech_###_id_fGTgRpdVxW4_523.36-554.85", # (1)
    "speech_###_id_FsJzj0Jyu5c_283.75-308.90", # (1)
    "speech_###_id_rtWATtjAFUM_29.58-58.15", # (1)
    "speech_###_id_HsmMuItrHj0_65.45-89.70", # (1)
    # 10 items
    "edu_###_edu01897", # (5)
    "edu_###_edu01931", # (5)
    # 10 items
    "factchecking_###_24149", # (5)
    "factchecking_###_23992", # (5)
],

"zho_Hans": [
    # Chinese source (50 items, 20 docs)
    # 23 items
    "news_###_rfi-chinese.50074", # (8)
    "news_###_chinese.macao.34804", # (5)
    "news_###_jingji_guancha_bao-zh-01.54568", # (10)
    # 15 items
    "social_###_116327380547232238", # (3)
    "social_###_116274093136237409", # (3)
    "social_###_116336026708955324", # (3)
    "social_###_116361286357084513", # (3)
    "social_###_116284435170089445", # (3)
    # 12 items
    "speech_###_id_EqGUUduWoYU_243.37-271.61", # (1)
    "speech_###_id_WTYpFmPaKEA_0.00-25.93", # (1)
    "speech_###_id_LtqVeFrqgyM_353.76-385.99", # (1)
    "speech_###_id_02AW2rIPWOc_356.02-381.50", # (1)
    "speech_###_id_EKcZJKu6KhU_361.82-384.15", # (1)
    "speech_###_id_gdcQiPngSFw_0.00-23.21", # (1)
    "speech_###_id_R6gOvpxDk2c_315.75-349.12", # (1)
    "speech_###_id_6XwpD5dgkfY_398.36-432.16", # (1)
    "speech_###_id_Za6c0NcAmOk_0.00-32.89", # (1)
    "speech_###_id_bnoXo9Rkdr8_563.75-599.64", # (1)
    "speech_###_id_jhrtaxMCcOE_150.57-176.26", # (1)
    "speech_###_id_pnmynTaF6P0_93.25-120.89", # (1)
],
}

VERSION = "v3"
os.makedirs(f"campaigns/{VERSION}", exist_ok=True)

for (lang1, lang2), data_lang in data_all.items():
    data_campaign = []
    print(lang1, lang2)
    for doc_id, data_doc in data_lang.items():
        domain = data_doc["domain"]
        pearmut_doc = [
          {
            "src": data_doc["src"][i],
            "src_text": data_doc["src_text"][i],
            "tgt": {
                model: model_tgt[i]
                for model, model_tgt in data_doc["tgt"].items()
            },
            # item_id also contains the domain
            "item_id": doc_id + f"_###_{i}",
            "instructions": (
                f"<div class='white-box' style='background:#d6d0bb; border-radius:8px; "
                f"padding:10px 15px; margin-top:-80px; margin-bottom:20px; margin-right:10px;'>"
                f"{INSTRUCTIONS_DOMAIN[domain]}"
                f"</div>"
            ),
          }
          for i in range(len(data_doc["src"]))
        ]
        # don't double-store src_text
        for line_i, line in enumerate(pearmut_doc):
            if line["src"] == line["src_text"]:
                line.pop("src_text")
            if line_i != 0:
                line.pop("instructions")
        data_campaign.append(pearmut_doc)

    # load per-language tutorial
    tutorial_name = LANG_TO_TUTORIAL[f"{lang1}---{lang2}"]
    with open(f"../pearmut/examples/tutorials/cesa_{tutorial_name}.json", "r") as f:
        data_tutorial = json.load(f)["data"][0]

    # load attention checks
    data_attention_checks = make_random_attn_checks(lang1, lang2, checks_num=5, data_lang=data_lang)

    GLOBAL_STYLE = (
        "#progress_div {width: 300px!important;} "
        "#instructions_global {width: calc(100% - 305px)!important;} "
        "video { width: 100%; }"
        "img { width: 100%; }"
    )
    
    # force right alignment for arabic
    if lang2 in {"arz_Arab", "arz"}:
        GLOBAL_STYLE += (
            ".output_tgt { direction: rtl !important; text-align: right !important; } "
        )

    # randomly order this campaign
    # make sure we have found these documents
    coldstart_ids = COLDSTART_PRIORITY[lang1]
    item_ids_0 = {doc[0]["item_id"].removesuffix("_###_0") for doc in data_campaign}
    assert len([item_id for item_id in coldstart_ids if item_id in item_ids_0]) == len(coldstart_ids), f"Not enough coldstart items for {lang1}---{lang2}"
    # put certain documents first but shuffle the rest
    random.Random(0).shuffle(data_campaign)
    data_campaign.sort(
        key=lambda doc: doc[0]["item_id"].removesuffix("_###_0") in coldstart_ids,
        reverse=True
    )

    campaign_definition = {
        "info": {
            "assignment": "dynamic",
            "protocol": "cESA",
            "shuffle": True,
            "dynamic_models": 3,
            "dynamic_coldstart": 20,
            "dynamic_coldstart_pool": 20,
            "word_level": lang2 not in {"jpn_Jpan", "tha_Thai", "zho_Hant", "zho_Hans", "zho_Hant_TW"},
            "special_tokens": ["[missing]", "[instructions fault]"],
            # we have only 2 attention checks and once they're exhausted no attention checks will be shown
            "data_random_prob": 0.2,
            "instructions": PROTOCOL_INSTRUCTIONS + "<style>" + GLOBAL_STYLE + "</style>",
            "users": (
                60 if f"{lang1}---{lang2}" in {"eng_Latn---arz_Arab", "eng_Latn---rus_Cyrl", "eng_Latn---ukr_Cyrl"}
                else 30
            ),
            "docs_per_user": (
                200 if lang2 in {"hye_Armn", "bel_Cyrl", "kaz_Cyrl"}
                else 30 if f"{lang1}---{lang2}" in {"eng_Latn---arz_Arab", "eng_Latn---rus_Cyrl", "eng_Latn---ukr_Cyrl"}
                else None
            ),
            "show_progress": False,
        },
        "campaign_id": f"{lang1}---{lang2} {VERSION}",
        "data": data_campaign,
        "data_welcome": data_tutorial,
        "data_random": data_attention_checks,
    }


    # dont save running campaigns
    if f"{lang1}---{lang2}" not in {
        "eng_Latn---sme_Latn",
        # "eng_Latn---ukr_Cyrl",

        # "eng_Latn---lld_Latn",
        # "eng_Latn---lij_Latn",
        # "eng_Latn---deu_Latn",
        # "eng_Latn---jpn_Jpan",
        # "eng_Latn---kor_Hang",
    }:
        continue

    print(lang1, lang2, "x")

    with open(f"campaigns/{VERSION}/{lang1}---{lang2}.json", "w") as f:
        json.dump(campaign_definition, f, indent=2, ensure_ascii=False)


# %%

# sanity check

import glob

for fname in glob.glob(f"campaigns/{VERSION}/*sme*.json"):
    with open(fname, "r") as f:
        data_campaign = json.load(f)
    print(fname, len(data_campaign["data"]), "documents")
    domain_count = collections.Counter([
        doc[0]["item_id"].split("_###_")[0]
        for doc in data_campaign["data"]
    ])
    print("Domain distribution (docs):", ", ".join([f"{domain} ({count})" for domain, count in domain_count.most_common()]))
    domain_count = collections.Counter([
        item["item_id"].split("_###_")[0]
        for doc in data_campaign["data"]
        for item in doc
    ])
    print("Domain distribution (segments):", ", ".join([f"{domain} ({count})" for domain, count in domain_count.most_common()]))

    first_item_models = set(data_campaign["data"][0][0]["tgt"].keys())
    assert all(set(item["tgt"].keys()) == first_item_models for doc in data_campaign["data"] for item in doc)
    print("Models:", ", ".join(first_item_models))
    coldstart_items = [
        (doc[0]["item_id"].split("_###_")[0], len(doc))
        for doc in data_campaign["data"][:20]
    ]
    coldstart_items_agg = collections.defaultdict(list)
    for domain, count in coldstart_items:
        coldstart_items_agg[domain].append(count)
    print("Coldstart:", ", ".join([f"{domain} ({"+".join([str(c) for c in counts])})" for domain, counts in coldstart_items_agg.items()]))
    print()