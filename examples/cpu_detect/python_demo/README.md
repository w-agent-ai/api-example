# Python CPU And ONNX Demos

This directory contains three Python demos and one shared NumPy implementation.

```text
image_detect_demo.py      image detection demo, embedded v0 weights
video_sequence_demo.py    video-to-gait-sequence demo, embedded v0 weights
onnx_demo.py              ONNX image demo through OpenCV DNN
persondet_numpy.py        shared pure NumPy detector/tracking implementation
persondet_weights.py      embedded v0 weights
```

The embedded-weight demos do not use PyTorch, ONNX Runtime, or runtime model
files. The current v0 weights are embedded in `persondet_weights.py`.

Generate the embedded weight file after updating C++ weights:

```bash
python3 python_demo/export_python_weights.py
```

Image detection:

```bash
python3 python_demo/image_detect_demo.py image.jpg
```

Video-to-gait-sequence extraction:

```bash
python3 python_demo/video_sequence_demo.py video.mp4
```

The video output directory is `video_gait_sequences/`. The Python version is
for correctness and integration checks; the C++ version is the fast deployment
path.

ONNX model demo using OpenCV DNN. This path does load the ONNX model at runtime:

```bash
python3 python_demo/onnx_demo.py image.jpg
```

This loads `onnx/gait_detect_dynamic_slim.onnx` at runtime, letterboxes input to
`640x640`, uses RGB `/255`, and decodes output as
`x_center, y_center, width, height, score`.

OpenCV version note:

```text
Python cv2 4.12.0: tested, works
C++ OpenCV 4.2.0: tested, cannot import this ONNX model
Recommended OpenCV for ONNX demo: 4.8+; 4.12+ is preferred
```

If the system `python3` does not have a recent enough OpenCV wheel, use a
Python environment with a newer `cv2` package:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip opencv-python numpy
python3 python_demo/onnx_demo.py image.jpg
```

Speed notes:

```text
- `image_detect_demo.py` and `video_sequence_demo.py` do not use PyTorch/ONNX Runtime.
- Forward uses NumPy arrays and OpenCV filtering on CPU.
- There is no hand-written SIMD path like cpp/persondet.cpp.
- NumPy/OpenCV themselves may still use optimized native code internally.
```

Useful CPU-side speed levers:

```text
1. Keep resize_width at 640 or lower it if accuracy allows.
2. Keep score_threshold at 0.30 so NMS does not process too many boxes.
3. Keep video jump enabled; the script targets 10-20 effective FPS.
4. Use the C++ demo for real speed-critical deployment.
```
