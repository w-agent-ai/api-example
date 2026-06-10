# People Detection And Gait Sequence Demos

This repo currently contains four deployment/demo paths:

```text
1. C++ compiled-weight person detector
2. C++ video-to-gait-sequence extractor
3. Python/Numpy compiled-weight-style demo
4. ONNX model demos for C++ and Python
```

The default lightweight model is v0. Its weights are compiled into:

```text
cpp/persondet_weights.cpp
python_demo/persondet_weights.py
```

The stronger teacher/reference ONNX model is:

```text
onnx/gait_detect_dynamic_slim.onnx
```

## C++ Build

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build -j
```

For cross-compilation or portable release binaries, disable local CPU-specific
code generation:

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release -DPERSONDET_ENABLE_NATIVE=OFF
```

Built demos:

```text
cpp/build/image_detect_demo      image detection demo, compiled v0 weights
cpp/build/video_sequence_demo    video to gait sequence folders
cpp/build/onnx_demo              ONNX image demo via OpenCV DNN
```

## C++ Single Image

```bash
cpp/build/image_detect_demo image.jpg out.jpg 640 0.30
```

Output boxes are drawn into `out.jpg`. The detector input is resized to width
640 and height is rounded to a multiple of 32.

## C++ Video To Gait Sequences

```bash
cpp/build/video_sequence_demo video.mp4
```

Output:

```text
video_gait_sequences/
  video_seq000001_track000003/
    frame_000120.jpg
    frame_000122.jpg
    ...
    meta.txt
```

The video demo:

```text
- starts with default_jump = 2
- adjusts jump so effective processed FPS is between 10 and 20 when possible
- ignores boxes smaller than 64x128 pixels
- filters static tracks before writing sequences
- saves one gait sequence per folder
```

## Python/Numpy Demo

This path does not use PyTorch or ONNX Runtime. It uses embedded weights and
NumPy/OpenCV CPU operations.

```bash
python3 python_demo/image_detect_demo.py image.jpg
python3 python_demo/video_sequence_demo.py video.mp4
```

After updating `cpp/persondet_weights.cpp`, regenerate Python embedded weights:

```bash
python3 python_demo/export_python_weights.py
```

## ONNX Demos

Python ONNX demo:

```bash
python3 python_demo/onnx_demo.py image.jpg
```

C++ ONNX demo:

```bash
cpp/build/onnx_demo image.jpg onnx_result.jpg onnx/gait_detect_dynamic_slim.onnx
```

The ONNX preprocessing/decoding is:

```text
input: letterbox to 640x640
format: RGB, float32, /255
output: x_center, y_center, width, height, score
score threshold: 0.30
NMS threshold: 0.45
```

OpenCV version note:

```text
C++ OpenCV 4.2.0: tested, cannot import this ONNX model
Python cv2 4.12.0: tested, works
Recommended C++ OpenCV: 4.8+; 4.12+ is preferred
```

The C++ ONNX demo compiles with older OpenCV, but this specific ONNX requires a
newer OpenCV DNN importer. The Python demo works when `cv2.dnn` can import this
ONNX model.

## Deployment Notes

For the lightweight compiled-weight C++ detector, the SDK integration files are:

```text
cpp/persondet.h
cpp/persondet.cpp
cpp/persondet_weights.cpp
```

The detector core has no OpenCV, PyTorch, ONNX, or runtime model-file
dependency. OpenCV is only used by demos for image/video IO and drawing.

SIMD and OpenMP behavior:

```text
- x86/x64: AVX2/FMA is used when compiler target macros enable it
- ARM/Apple/Android: NEON is used when available
- OpenMP is used if enabled by the compiler
- default OpenMP threads: half CPU cores, capped at 16
```

For speed-critical deployment, use the C++ compiled-weight path. The Python
demo is mainly for correctness checks and easier reading.
