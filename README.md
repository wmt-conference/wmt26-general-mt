# WMT26 General Translation Shared Task

This repository contains the data for the WMT26 General Translation Shared Task testset as well as the corresponding collected human annotation and how to reproduce them.
TODO: description of GenMT data

# Human Evaluation

- The collected human annotations for WMT26 can be [found here as data](https://github.com/wmt-conference/wmt26-humeval/releases/tag/Data).
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
wget https://github.com/wmt-conference/wmt26-humeval/releases/download/Data/campaign_sources.zip -O campaign_sources.zip; unzip campaign_source.zip -d campaigns/
wget https://github.com/wmt-conference/wmt26-humeval/releases/download/Data/multimodal_inputs.zip -O multimodal_inputs.zip; unzip multimodal_inputs.zip -d data/assets/
# add campaigns
pearmut add campaigns/*.json
# run
pearmut run
```

## Loading human evaluation with completed annotations

You can also start the server with the existing annotations from WMT26

```bash
# install pearmut, potentially "pearmut==1.1.6"
pip install pearmut
# download campaign sources and multimedia assets
mkdir -p campaigns/ data/assets/
wget https://github.com/wmt-conference/wmt26-humeval/releases/download/Data/campaign_sources.zip -O campaign_sources.zip; unzip campaign_source.zip -d campaigns/
wget https://github.com/wmt-conference/wmt26-humeval/releases/download/Data/multimodal_inputs.zip -O multimodal_inputs.zip; unzip multimodal_inputs.zip -d data/assets/
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
