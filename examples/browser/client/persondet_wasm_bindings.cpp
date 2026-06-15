#include "persondet.h"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <vector>

namespace {

struct WasmDetector {
    std::vector<float> results;
    std::unique_ptr<persondet::Detector> detector;

    explicit WasmDetector(int max_results) : results((size_t)std::max(1, max_results) * 5) {
        detector.reset(new persondet::Detector(results.data(), std::max(1, max_results)));
    }
};

}  // namespace

extern "C" {

void* persondet_create(int max_results) {
    try {
        return new WasmDetector(max_results);
    } catch (...) {
        return nullptr;
    }
}

void persondet_destroy(void* handle) {
    delete static_cast<WasmDetector*>(handle);
}

int persondet_detect_rgba(
    void* handle,
    const unsigned char* rgba,
    int width,
    int height,
    float score_threshold,
    float nms_threshold,
    int topk) {
    if (!handle || !rgba || width <= 0 || height <= 0) {
        return 0;
    }
    std::vector<unsigned char> bgr((size_t)width * height * 3);
    for (int y = 0; y < height; ++y) {
        const unsigned char* src = rgba + (size_t)y * width * 4;
        unsigned char* dst = bgr.data() + (size_t)y * width * 3;
        for (int x = 0; x < width; ++x) {
            dst[x * 3 + 0] = src[x * 4 + 2];
            dst[x * 3 + 1] = src[x * 4 + 1];
            dst[x * 3 + 2] = src[x * 4 + 0];
        }
    }
    auto* det = static_cast<WasmDetector*>(handle);
    return det->detector->detect_bgr(bgr.data(), width, height, width * 3, score_threshold, nms_threshold, topk);
}

const float* persondet_results(void* handle) {
    if (!handle) {
        return nullptr;
    }
    return static_cast<WasmDetector*>(handle)->results.data();
}

}
