# Object Search

Use this recipe when the user wants to find objects or people in one image from
a text prompt, for example "person in red" or "bus".

## Use

- Call `POST /v1/object-search`.
- Send raw `image_base64` without a `data:image/...;base64,` prefix.
- Send `prompt` as the target description.
- Read `boxes[]`.

## Output Rules

- `boxes` are pixel coordinates in the uploaded image.
- `x1,y1` is top-left and `x2,y2` is bottom-right.
- No match returns `boxes: []` and is not an error.
- `label` is model-generated and is not a fixed taxonomy.

## Run

```bash
pip install requests
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/registered/python/object_search_api_demo.py examples/sample_sequences/ID_0001/001811.jpg 'person'
```
