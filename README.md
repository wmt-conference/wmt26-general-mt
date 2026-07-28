# WMT26 General Translation Shared Task

This repository contains the data for the WMT26 General Translation Shared Task testset as well as the corresponding collected human annotation and how to reproduce them.

# Testset and Translations

## Test data

The `data/wmt26-genmt.jsonl` contains the test data in JSONL format. Each line includes the following fields:

- `doc_id`: A unique identifier in the following format: `set_id_###_domain_###_src_lang_###_tgt_lang_###_doc_id`.
- `domain`.
- `src_lang`.
- `tgt_lang`.
- `src_text`.
- `video`: For speech samples, a dictionary containing the original asset `id` and its `path`; `null` for the other domains.
- `screenshot`: For social documents with screenshots, a dictionary containing the original asset `id` and its `path`; `null` otherwise.
- `gold_transcript`: For speech samples, `src_text` contains an ASR-generated transcript of the source video, while `gold_transcript` contains a manually-curated transcript.
- `prompt_instruction`: Default translation instruction provided to participants.
- `multimodal_instruction`: Default translation instruction that uses the multimedia content (where available).
- `evaluation_instruction`: Domain-specific evaluation guidance provided to human evaluators.
- `refs`: A dictionary containing all available human reference translations, or `{}` if the sample has no reference.

Paths to multimedia content (video and screenshots) are relative to the [assets folder](https://data.statmt.org/wmt26/wmt26_genmt_blindset_multimodal_inputs.zip) released to participants at submission time.

## System submissions

Each translation system has a corresponding JSONL file containing the following fields:

- `doc_id`: The identifier of the corresponding test set entry in `data/wmt26-genmt.jsonl`.
- `hypothesis`: The submitted translation;
- `metadata`: A dictionary containing information such as the number of input and output tokens used to generate the translation, generation parameters values, and the generated reasoning trace. The contents of `metadata` may vary across systems.

# Human Evaluation

- The collected human annotations for WMT26 can be [found here as data](https://github.com/wmt-conference/wmt26-general-mt/releases/tag/humeval).
- Alternatively, you can browse the completed annotations [interactively](TODO) from the annotator perspective.

The human evaluation at WMT is done with the [Pearmut tool](https://github.com/zouharvi/pearmut) which you'll need to have installed if you wish to replicate them.
This repository is intended for the specific WMT human evaluation campaign.
If you simply wish to run your own human evaluation in a similar setup, please refer to the [Pearmut tool documentation](https://github.com/zouharvi/pearmut) instead and use the "Contrastive Error Span Annotation (cESA)" protocol.
The specific version that was used for WMT26 is 1.1.6, though future version _may_ be compatible.

## Re-running human evaluation

You can start the annotation server without any completed annotations as follows:

```bash
# install pearmut, potentially "pearmut==1.1.6"
pip install pearmut
# download campaign sources and multimedia assets
mkdir -p campaigns/ data/assets/
wget https://github.com/wmt-conference/wmt26-general-mt/releases/download/humeval/campaign_sources.zip -O campaign_sources.zip; unzip campaign_source.zip -d campaigns/
wget https://github.com/wmt-conference/wmt26-general-mt/releases/download/humeval/multimodal_inputs.zip -O multimodal_inputs.zip; unzip multimodal_inputs.zip -d data/assets/
# add campaigns
pearmut add campaigns/*.json
# run
pearmut run
```

## Loading human evaluation with completed annotations

You can also start the server with the existing annotations from WMT26:

```bash
# install pearmut, potentially "pearmut==1.1.6"
pip install pearmut
# download campaign sources and multimedia assets
mkdir -p campaigns/ data/assets/
wget https://github.com/wmt-conference/wmt26-general-mt/releases/download/humeval/campaign_sources.zip -O campaign_sources.zip; unzip campaign_source.zip -d campaigns/
wget https://github.com/wmt-conference/wmt26-general-mt/releases/download/humeval/multimodal_inputs.zip -O multimodal_inputs.zip; unzip multimodal_inputs.zip -d data/assets/
wget TODO -O annotations.json
wget TOOD -O progress.json
# add campaigns and existing annotations
# use -o to overwrite if you followed previous section
pearmut add-existing campaigns/* --annotations annotations.json --progress progress.json 
# run
pearmut run
```

## Preparing campaign files from source

To prepare the campaign sources based on GenMT blindset, you will need access to the internal repository.
This is meant for WMT organizers, not other researchers.
Do not attempt this unless you're a WMT organizer that is trying to reuse this process e.g. for WMT27.
```bash
git clone --depth 1 git@github.com:wmt-conference/wmt26-generalmt-internal.git wmt26-generalmt-internal
python3 01-prepare_campaigns.py
ls campaigns/v3/
```

Then you can proceed with adding the campaigns
```bash
pearmut add campaigns/v3/*
```
