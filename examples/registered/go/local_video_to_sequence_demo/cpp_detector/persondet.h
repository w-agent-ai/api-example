#pragma once

// Portable C++17 CPU person detector.
//
// To integrate the detector into another project, copy exactly these files:
//   persondet.h
//   persondet.cpp
//   persondet_weights.cpp
//
// The core detector has no OpenCV/PyTorch/model-file dependency. The caller is
// responsible for image decode and resize. detect_bgr() expects tightly or
// strided BGR uint8 image memory, usually resized to width 640 with height
// rounded to a multiple of 32.
//
// SIMD is selected automatically from compiler target macros:
//   x86/x64: AVX2/FMA when the compiler target enables them
//   ARM/Apple/Android: NEON when available
//   otherwise: scalar C++
//
// OpenMP is used automatically if this translation unit is compiled with
// OpenMP enabled. The default thread count is half of CPU cores, capped at 16,
// unless OMP_NUM_THREADS is set by the caller.

namespace persondet {

class Detector {
public:
    // result_buffer stores result_buffer_count boxes. Each box uses 5 floats:
    // x, y, w, h, score.
    Detector(float* result_buffer, int result_buffer_count);
    ~Detector();

    // bgr is expected to be already resized by the caller. Output boxes are in
    // the same coordinate system as this input image. This matches OpenCV image
    // memory directly and does not do cvtColor or channel swapping internally.
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

namespace builtin {

struct WeightBlob {
    const char* name;
    const float* data;
    unsigned int count;
    const unsigned int* shape;
    unsigned int ndim;
};

extern const WeightBlob kWeights[];
extern const unsigned int kWeightCount;

}  // namespace builtin

}  // namespace persondet
