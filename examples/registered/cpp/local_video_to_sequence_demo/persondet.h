#pragma once

// Portable C++17 CPU person detector backed by ONNX Runtime CPU.
//
// To integrate the detector into another project, copy exactly these files:
//   persondet.h
//   persondet.cpp
//   gait_detect.onnx
//   third_party/onnxruntime-linux-x64/
//
// The detector loads gait_detect.onnx once in the constructor. It accepts
// normal OpenCV BGR uint8 image memory and internally resizes to the model's
// fixed input size 1x3x352x640. Output boxes are mapped back to the caller's
// input image coordinate system.

namespace persondet {

class Detector {
public:
    // result_buffer stores result_buffer_count boxes. Each box uses 5 floats:
    // x, y, w, h, score.
    Detector(float* result_buffer, int result_buffer_count);
    ~Detector();

    // bgr is normal BGR uint8 image memory. Output boxes are in the same
    // coordinate system as this input image. This matches OpenCV image memory
    // directly and does not do cvtColor or channel swapping internally.
    int detect_bgr(
        const unsigned char* bgr,
        int width,
        int height,
        int stride,
        float score_threshold = 0.35f,
        float nms_threshold = 0.50f,
        int topk = 1000);

private:
    struct Impl;
    Impl* impl_;
};

}  // namespace persondet
