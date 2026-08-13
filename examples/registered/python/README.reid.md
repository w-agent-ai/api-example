# Python ReID API Demo

This package only demonstrates ReID feature extraction.

## Setup

```bash
pip install requests
```

## Usage

1. Prepare one cropped person image.
2. Open `reid_feature_demo/reid_feature_api_demo.py`.
3. Edit `API_KEY` and `IMAGE_PATH`, or pass an image path at runtime.
4. Run:

```bash
python3 reid_feature_demo/reid_feature_api_demo.py /path/to/person.jpg
```

The script calls `POST /v1/features/reid` and returns a 512-dimensional ReID feature.

The input should be one person crop. If the original image contains multiple people, detect and crop the target person before calling this API.
