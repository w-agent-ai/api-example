# Same Person Identity

Use this recipe when the user wants to decide whether two tracked person
sequences are the same person.

## Use

- Parse each tracked person sequence with `POST /v1/sequences/{task_id}/parse`.
- Read features from `response.sequences[]`.
- Compare only same-type vectors:
  - `gait_feature` with `gait_feature`
  - `face_feature` with `face_feature`
  - `reid_feature` with `reid_feature`
- Similarity is dot product.

## Do Not Use

- Do not use raw image similarity for identity matching.
- Do not compare `gait_feature` with `reid_feature` or `face_feature`.
- Do not read `result.gait_feature` at the top level; parse returns
  `sequences[]`.

## Run

```bash
pip install requests
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/registered/python/sequence_similarity_demo.py examples/sample_sequences
```

## Output

The demo writes a pairwise similarity CSV for all sequence folders.
