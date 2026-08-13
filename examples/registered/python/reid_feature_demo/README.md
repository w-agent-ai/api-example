# ReID Python Demo

This demo shows the single-person-image-to-ReID-feature flow:

1. Read one cropped person image.
2. Call `POST /v1/features/reid`.
3. Print the 512-dimensional ReID feature and billing result.

Install dependencies:

```bash
pip install requests
```

Edit `API_KEY` at the top of `reid_feature_api_demo.py`, then run:

```bash
python3 reid_feature_api_demo.py /path/to/person.jpg
```

The input should be one person crop. If the original image contains multiple people, detect and crop the target person before calling this API.
