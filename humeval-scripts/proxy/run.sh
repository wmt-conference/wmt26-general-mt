# various management scripts

rsync campaigns/v3/*.json wmt-pearmut:campaigns/v3/ -avz
rsync wmt-pearmut:campaigns/v3/ campaigns/v3_upstream/ -avz

rsync wmt26-generalmt-internal/blindset/multimodal_inputs/ wmt-pearmut:data/assets/multimodal_inputs/ -avz
cp -r wmt26-generalmt-internal/blindset/multimodal_inputs/ data/assets/multimodal_inputs/

rsync wmt-pearmut:data/assets/multimodal_inputs/ wmt26-generalmt-internal/blindset/multimodal_inputs/ -avz

# "hotreload"
cd pearmut && \
git pull && \
cd .. && \
killall -2 pearmut && \
nohup pearmut run --port 80 --url "https://wmt.vilda.net/" &

pearmut run --port 80 --url "https://wmt.vilda.net/"
nohup pearmut run --port 80 --url "https://wmt.vilda.net/" &

killall -2 pearmut; nohup pearmut run --port 80 --url "https://wmt.vilda.net/" &

# load campaigns
pearmut add \
    campaigns/v3/wmt26-ces_Latn_deu_Latn.json \
    campaigns/v3/wmt26-ces_Latn_vie_Latn.json \
;