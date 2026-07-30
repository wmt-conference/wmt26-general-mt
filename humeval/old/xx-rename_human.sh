rename campaigns/wmt26-eng_Latn_lld_Latn.json to campaigns/eng_Latn---lld_Latn.json and all files there

for f in campaigns/v3/wmt26-*.json; do
    newname="$(echo "$f" | sed 's/wmt26-//; s/_/---/2')"
    mv $f $newname
done


cp -r data/ data_backup/2026-07-17/

sed -i 's/\"human\":/\"Human (from scratch)\":/g' "data/campaigns/eng_Latn---lld_Latn v3.json"
sed -i 's/\"human\":/\"Human (from scratch)\":/g' "data/progress/eng_Latn---lld_Latn v3.json"
sed -i 's/\"human\":/\"Human (from scratch)\":/g' "data/annotations/eng_Latn---lld_Latn v3.jsonl"
sed -i 's/\"human\":/\"Human (from scratch)\":/g' "campaigns/v3/eng_Latn---lld_Latn.json"

sed -i 's/\"human\":/\"Human (from scratch)\":/g' "data/campaigns/eng_Latn---lij_Latn v3.json"
sed -i 's/\"human\":/\"Human (from scratch)\":/g' "data/progress/eng_Latn---lij_Latn v3.json"
sed -i 's/\"human\":/\"Human (from scratch)\":/g' "data/annotations/eng_Latn---lij_Latn v3.jsonl"
sed -i 's/\"human\":/\"Human (from scratch)\":/g' "campaigns/v3/eng_Latn---lij_Latn.json"

sed -i 's/\"human\":/\"Human (postediting)\":/g' "data/campaigns/eng_Latn---deu_Latn v3.json"
sed -i 's/\"human\":/\"Human (postediting)\":/g' "data/progress/eng_Latn---deu_Latn v3.json"
#sed -i 's/\"human\":/\"Human (postediting)\":/g' "data/annotations/eng_Latn---deu_Latn v3.jsonl"
sed -i 's/\"human\":/\"Human (postediting)\":/g' "campaigns/v3/eng_Latn---deu_Latn.json"

sed -i 's/\"human\":/\"Human (postediting)\":/g' "data/campaigns/eng_Latn---jpn_Jpan v3.json"
sed -i 's/\"human\":/\"Human (postediting)\":/g' "data/progress/eng_Latn---jpn_Jpan v3.json"
sed -i 's/\"human\":/\"Human (postediting)\":/g' "data/annotations/eng_Latn---jpn_Jpan v3.jsonl"
sed -i 's/\"human\":/\"Human (postediting)\":/g' "campaigns/v3/eng_Latn---jpn_Jpan.json"

# get them back!
rsync wmt-pearmut:campaigns/v3/ campaigns/v3/ -avz

# push to Greg and WMT-Metrics!