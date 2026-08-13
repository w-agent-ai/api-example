#include "facedetectcnn.h"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <vector>

namespace {

constexpr int kFieldsPerFace = 15;

struct WasmFaceDetector {
    std::vector<unsigned char> buffer;
    std::vector<float> results;

    explicit WasmFaceDetector(int max_results)
        : buffer(FACEDETECTION_RESULT_BUFFER_SIZE),
          results(static_cast<size_t>(std::max(1, max_results)) * kFieldsPerFace) {}
};

}  // namespace

extern "C" {

void* facedet_create(int max_results) {
    try {
        return new WasmFaceDetector(max_results);
    } catch (...) {
        return nullptr;
    }
}

void facedet_destroy(void* handle) {
    delete static_cast<WasmFaceDetector*>(handle);
}

int facedet_detect_rgba(void* handle, const unsigned char* rgba, int width, int height, int max_results) {
    if (!handle || !rgba || width <= 0 || height <= 0 || max_results <= 0) {
        return 0;
    }
    std::vector<unsigned char> bgr(static_cast<size_t>(width) * static_cast<size_t>(height) * 3);
    for (int y = 0; y < height; ++y) {
        const unsigned char* src = rgba + static_cast<size_t>(y) * width * 4;
        unsigned char* dst = bgr.data() + static_cast<size_t>(y) * width * 3;
        for (int x = 0; x < width; ++x) {
            dst[x * 3 + 0] = src[x * 4 + 2];
            dst[x * 3 + 1] = src[x * 4 + 1];
            dst[x * 3 + 2] = src[x * 4 + 0];
        }
    }
    auto* det = static_cast<WasmFaceDetector*>(handle);
    std::fill(det->results.begin(), det->results.end(), 0.0f);
    int* raw = facedetect_cnn(det->buffer.data(), bgr.data(), width, height, width * 3);
    int count = raw ? *raw : 0;
    count = std::max(0, std::min(count, max_results));
    count = std::min(count, static_cast<int>(det->results.size() / kFieldsPerFace));
    for (int i = 0; i < count; ++i) {
        short* p = reinterpret_cast<short*>(raw + 1) + FACEDETECTION_RESULT_STRIDE_SHORTS * i;
        float* out = det->results.data() + static_cast<size_t>(i) * kFieldsPerFace;
        for (int j = 0; j < kFieldsPerFace; ++j) {
            out[j] = static_cast<float>(p[j]);
        }
    }
    return count;
}

const float* facedet_results(void* handle) {
    if (!handle) {
        return nullptr;
    }
    return static_cast<WasmFaceDetector*>(handle)->results.data();
}

}
