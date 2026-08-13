# Python Face Recognition API Demo

This package only demonstrates face recognition.

## Setup

```bash
pip install requests opencv-python numpy onnxruntime
```

## Usage

1. Open `face_feature_demo/face_feature_api_demo.py`.
2. Edit the top-level `API_KEY`.
3. Run:

```bash
python3 face_feature_demo/face_feature_api_demo.py /path/to/image.jpg
```

The script uses the included `face_detect.onnx` model to detect a face and 5 landmarks locally, aligns the face crop, then calls `POST /v1/features/face` to return a 512-dimensional face feature.

The server API expects an aligned face image. Detection and alignment happen in this local demo.
