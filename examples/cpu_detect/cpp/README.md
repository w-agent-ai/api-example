# C++ Demos

This directory contains the C++ demo code and the lightweight compiled-weight
person detector.

## Files

```text
persondet.h               detector API
persondet.cpp             detector implementation
persondet_weights.cpp     embedded v0 weights
image_detect_demo.cpp     image detection demo for compiled-weight detector
video_sequence_demo.cpp   video-to-gait-sequence demo
onnx_demo.cpp             ONNX image demo through OpenCV DNN
CMakeLists.txt            build file
```

For SDK integration of the lightweight detector, copy only:

```text
persondet.h
persondet.cpp
persondet_weights.cpp
```

The detector core does not depend on OpenCV, PyTorch, ONNX, or any runtime
model file. OpenCV is only used by demos for image/video IO and drawing.

## Build

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build -j
```

For cross-compilation or portable release binaries, disable local CPU-specific
code generation:

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release -DPERSONDET_ENABLE_NATIVE=OFF
```

If OpenCV is found, these executables are built:

```text
cpp/build/image_detect_demo
cpp/build/video_sequence_demo
cpp/build/onnx_demo
```

## Single Image

```bash
cpp/build/image_detect_demo image.jpg out.jpg 640 0.30
```

Arguments:

```text
image.jpg       input image
out.jpg         output image with boxes
640             resize width; height is rounded to a multiple of 32
0.30            score threshold
```

## Video To Gait Sequences

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

Fixed behavior in `video_sequence_demo.cpp`:

```text
default_jump = 2
effective processed FPS is adjusted to 10-20 when possible
boxes smaller than 64x128 pixels are ignored
static tracks are filtered before writing
one sequence is saved per folder
```

## ONNX Image Demo

```bash
cpp/build/onnx_demo image.jpg onnx_result.jpg onnx/gait_detect_dynamic_slim.onnx
```

The ONNX demo:

```text
loads the ONNX file at runtime
letterboxes input to 640x640
uses RGB float32 / 255
decodes output as x_center, y_center, width, height, score
uses score threshold 0.30 and NMS threshold 0.45
```

This path depends on OpenCV DNN's ONNX importer.

```text
C++ OpenCV 4.2.0: tested, cannot import this ONNX model
Python cv2 4.12.0: tested, works
Recommended C++ OpenCV: 4.8+; 4.12+ is preferred
```

The C++ demo may compile with older OpenCV, but this specific ONNX needs a
newer OpenCV DNN importer to run correctly. If the target machine only has an
old C++ OpenCV, use the Python ONNX demo or rebuild OpenCV.

## API

```cpp
#include "persondet.h"

float results[1024 * 5];
persondet::Detector detector(results, 1024);

int count = detector.detect_bgr(
    bgr_data,
    width,
    height,
    bgr_stride_bytes,
    0.30f,
    0.45f,
    1000);

for (int i = 0; i < count; ++i) {
    const float* r = results + i * 5;
    float x = r[0];
    float y = r[1];
    float w = r[2];
    float h = r[3];
    float score = r[4];
}
```

Each result uses five floats:

```text
x, y, width, height, score
```

`detect_bgr()` expects BGR `uint8` image memory and does not resize internally.
The caller controls preprocessing.

## CPU Behavior

Compile as C++17.

```text
x86/x64: AVX2/FMA is selected when compiler target macros enable it
ARM/Apple/Android: NEON is selected when available
fallback: scalar C++
OpenMP: used when enabled by compiler
default OpenMP threads: half CPU cores, capped at 16
```

Example compile commands for embedding the detector core:

```bash
c++ -std=c++17 -O3 -DNDEBUG -fopenmp persondet.cpp persondet_weights.cpp
c++ -std=c++17 -O3 -DNDEBUG -march=native -fopenmp persondet.cpp persondet_weights.cpp
cl /std:c++17 /O2 /openmp /arch:AVX2 persondet.cpp persondet_weights.cpp
clang++ -std=c++17 -O3 -DNDEBUG persondet.cpp persondet_weights.cpp
```
