# Face Recognition Python Demo

This demo shows the full local-image-to-face-feature flow:

1. Read one image.
2. Load `face_detect.onnx` with ONNX Runtime CPU.
3. Detect the best face and 5 landmarks.
4. Align and crop the face by eye landmarks.
5. Call `POST /v1/features/face` to get a 512-dimensional face feature.

Install dependencies:

```bash
pip install requests opencv-python numpy onnxruntime
```

Edit `API_KEY` at the top of `face_feature_api_demo.py`, then run:

```bash
python3 face_feature_api_demo.py /path/to/image.jpg
```

The server expects an aligned face crop. Face detection and alignment happen locally in this demo.
