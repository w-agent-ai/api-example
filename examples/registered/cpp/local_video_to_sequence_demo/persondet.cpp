#include "persondet.h"

#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(__linux__)
#include <limits.h>
#include <unistd.h>
#endif

namespace persondet {
namespace {

constexpr const char* kModelName = "gait_detect.onnx";
constexpr int kModelWidth = 640;
constexpr int kModelHeight = 352;
constexpr int kModelChannels = 3;

struct Box {
    float x1 = 0.0f;
    float y1 = 0.0f;
    float x2 = 0.0f;
    float y2 = 0.0f;
    float score = 0.0f;
};

float sigmoid(float x) {
    if (x >= 50.0f) return 1.0f;
    if (x <= -50.0f) return 0.0f;
    return 1.0f / (1.0f + std::exp(-x));
}

float iou(const Box& a, const Box& b) {
    const float xx1 = std::max(a.x1, b.x1);
    const float yy1 = std::max(a.y1, b.y1);
    const float xx2 = std::min(a.x2, b.x2);
    const float yy2 = std::min(a.y2, b.y2);
    const float w = std::max(0.0f, xx2 - xx1);
    const float h = std::max(0.0f, yy2 - yy1);
    const float inter = w * h;
    const float area_a = std::max(0.0f, a.x2 - a.x1) * std::max(0.0f, a.y2 - a.y1);
    const float area_b = std::max(0.0f, b.x2 - b.x1) * std::max(0.0f, b.y2 - b.y1);
    const float denom = area_a + area_b - inter;
    return denom > 0.0f ? inter / denom : 0.0f;
}

std::vector<int> nms(const std::vector<Box>& boxes, float threshold, int topk) {
    std::vector<int> order(boxes.size());
    for (int i = 0; i < static_cast<int>(boxes.size()); ++i) order[i] = i;
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        return boxes[a].score > boxes[b].score;
    });
    if (topk > 0 && static_cast<int>(order.size()) > topk) order.resize(topk);

    std::vector<int> keep;
    std::vector<char> removed(order.size(), 0);
    for (size_t i = 0; i < order.size(); ++i) {
        if (removed[i]) continue;
        const int idx = order[i];
        keep.push_back(idx);
        for (size_t j = i + 1; j < order.size(); ++j) {
            if (!removed[j] && iou(boxes[idx], boxes[order[j]]) > threshold) {
                removed[j] = 1;
            }
        }
    }
    return keep;
}

std::filesystem::path executableDir() {
#if defined(__linux__)
    std::array<char, PATH_MAX> buf{};
    const ssize_t n = readlink("/proc/self/exe", buf.data(), buf.size() - 1);
    if (n > 0) {
        buf[static_cast<size_t>(n)] = '\0';
        return std::filesystem::path(buf.data()).parent_path();
    }
#endif
    return std::filesystem::current_path();
}

std::filesystem::path findModelPath() {
    if (const char* env = std::getenv("W_AGENT_PERSONDET_ONNX")) {
        std::filesystem::path p(env);
        if (std::filesystem::exists(p)) return p;
    }
    const std::filesystem::path exe_dir = executableDir();
    const std::array<std::filesystem::path, 5> candidates = {
        exe_dir / kModelName,
        exe_dir.parent_path() / kModelName,
        exe_dir.parent_path().parent_path() / kModelName,
        std::filesystem::current_path() / kModelName,
        std::filesystem::path(__FILE__).parent_path() / kModelName,
    };
    for (const auto& p : candidates) {
        if (std::filesystem::exists(p)) return p;
    }
    throw std::runtime_error("person detector ONNX model not found: " + std::string(kModelName));
}

void resizeBGRToNCHW(const unsigned char* bgr, int width, int height, int stride, std::vector<float>& out) {
    out.assign(static_cast<size_t>(kModelChannels) * kModelHeight * kModelWidth, 0.0f);
    if (!bgr || width <= 0 || height <= 0 || stride <= 0) return;

    const float scale_x = static_cast<float>(width) / static_cast<float>(kModelWidth);
    const float scale_y = static_cast<float>(height) / static_cast<float>(kModelHeight);
    for (int y = 0; y < kModelHeight; ++y) {
        float src_y = (static_cast<float>(y) + 0.5f) * scale_y - 0.5f;
        src_y = std::max(0.0f, std::min(src_y, static_cast<float>(height - 1)));
        const int y0 = static_cast<int>(std::floor(src_y));
        const int y1 = std::min(y0 + 1, height - 1);
        const float wy = src_y - static_cast<float>(y0);
        for (int x = 0; x < kModelWidth; ++x) {
            float src_x = (static_cast<float>(x) + 0.5f) * scale_x - 0.5f;
            src_x = std::max(0.0f, std::min(src_x, static_cast<float>(width - 1)));
            const int x0 = static_cast<int>(std::floor(src_x));
            const int x1 = std::min(x0 + 1, width - 1);
            const float wx = src_x - static_cast<float>(x0);

            const unsigned char* p00 = bgr + static_cast<size_t>(y0) * stride + static_cast<size_t>(x0) * 3;
            const unsigned char* p01 = bgr + static_cast<size_t>(y0) * stride + static_cast<size_t>(x1) * 3;
            const unsigned char* p10 = bgr + static_cast<size_t>(y1) * stride + static_cast<size_t>(x0) * 3;
            const unsigned char* p11 = bgr + static_cast<size_t>(y1) * stride + static_cast<size_t>(x1) * 3;
            for (int c = 0; c < kModelChannels; ++c) {
                const float top = static_cast<float>(p00[c]) * (1.0f - wx) + static_cast<float>(p01[c]) * wx;
                const float bottom = static_cast<float>(p10[c]) * (1.0f - wx) + static_cast<float>(p11[c]) * wx;
                out[static_cast<size_t>(c) * kModelHeight * kModelWidth + static_cast<size_t>(y) * kModelWidth + x] =
                    top * (1.0f - wy) + bottom * wy;
            }
        }
    }
}

std::vector<Box> decodeOutput(const float* data, const std::vector<int64_t>& shape, int stride, float score_threshold) {
    std::vector<Box> out;
    if (!data || shape.size() != 4 || shape[0] != 1 || shape[1] < 5) return out;
    const int channels = static_cast<int>(shape[1]);
    const int h = static_cast<int>(shape[2]);
    const int w = static_cast<int>(shape[3]);
    const size_t plane = static_cast<size_t>(h) * w;
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            const size_t idx = static_cast<size_t>(y) * w + x;
            const float score = sigmoid(data[static_cast<size_t>(4) * plane + idx]);
            if (score < score_threshold) continue;
            const float tx = data[static_cast<size_t>(0) * plane + idx];
            const float ty = data[static_cast<size_t>(1) * plane + idx];
            const float tw = std::max(-8.0f, std::min(8.0f, data[static_cast<size_t>(2) * plane + idx]));
            const float th = std::max(-8.0f, std::min(8.0f, data[static_cast<size_t>(3) * plane + idx]));
            const float bw = std::exp(tw) * static_cast<float>(stride);
            const float bh = std::exp(th) * static_cast<float>(stride);
            const float cx = (static_cast<float>(x) + tx) * static_cast<float>(stride);
            const float cy = (static_cast<float>(y) + ty) * static_cast<float>(stride);
            Box box;
            box.x1 = std::max(0.0f, cx - bw * 0.5f);
            box.y1 = std::max(0.0f, cy - bh * 0.5f);
            box.x2 = std::min(static_cast<float>(kModelWidth), cx + bw * 0.5f);
            box.y2 = std::min(static_cast<float>(kModelHeight), cy + bh * 0.5f);
            box.score = score;
            if (box.x2 > box.x1 && box.y2 > box.y1) out.push_back(box);
        }
    }
    (void)channels;
    return out;
}

}  // namespace

struct Detector::Impl {
    explicit Impl(float* out, int out_count)
        : result_buffer(out),
          result_buffer_count(out_count),
          env(ORT_LOGGING_LEVEL_WARNING, "w-agent-persondet") {
        if (!result_buffer || result_buffer_count <= 0) {
            throw std::runtime_error("invalid person detector result buffer");
        }
        model_path = findModelPath();
        Ort::SessionOptions options;
        options.SetIntraOpNumThreads(1);
        options.SetInterOpNumThreads(1);
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        session = std::make_unique<Ort::Session>(env, model_path.string().c_str(), options);

        Ort::AllocatorWithDefaultOptions allocator;
        input_name = session->GetInputNameAllocated(0, allocator).get();
        const size_t output_count = session->GetOutputCount();
        output_names.reserve(output_count);
        output_name_ptrs.reserve(output_count);
        for (size_t i = 0; i < output_count; ++i) {
            output_names.emplace_back(session->GetOutputNameAllocated(i, allocator).get());
        }
        for (const auto& name : output_names) output_name_ptrs.push_back(name.c_str());
        std::cerr << "[persondet] onnxruntime cpu model=" << model_path << std::endl;
    }

    float* result_buffer = nullptr;
    int result_buffer_count = 0;
    std::filesystem::path model_path;
    Ort::Env env;
    std::unique_ptr<Ort::Session> session;
    std::string input_name;
    std::vector<std::string> output_names;
    std::vector<const char*> output_name_ptrs;
    std::vector<float> input_tensor;
};

Detector::Detector(float* result_buffer, int result_buffer_count)
    : impl_(new Impl(result_buffer, result_buffer_count)) {}

Detector::~Detector() {
    delete impl_;
}

int Detector::detect_bgr(
    const unsigned char* bgr,
    int width,
    int height,
    int stride,
    float score_threshold,
    float nms_threshold,
    int topk) {
    if (!impl_ || !impl_->session || !bgr || width <= 0 || height <= 0 || stride <= 0) return 0;

    resizeBGRToNCHW(bgr, width, height, stride, impl_->input_tensor);
    std::array<int64_t, 4> input_shape = {1, kModelChannels, kModelHeight, kModelWidth};
    Ort::MemoryInfo memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value input = Ort::Value::CreateTensor<float>(
        memory_info,
        impl_->input_tensor.data(),
        impl_->input_tensor.size(),
        input_shape.data(),
        input_shape.size());

    const char* input_names[] = {impl_->input_name.c_str()};
    std::vector<Ort::Value> outputs = impl_->session->Run(
        Ort::RunOptions{nullptr},
        input_names,
        &input,
        1,
        impl_->output_name_ptrs.data(),
        impl_->output_name_ptrs.size());

    std::vector<Box> boxes;
    const int strides[] = {8, 16, 32};
    for (size_t i = 0; i < outputs.size() && i < 3; ++i) {
        auto info = outputs[i].GetTensorTypeAndShapeInfo();
        std::vector<int64_t> shape = info.GetShape();
        const float* data = outputs[i].GetTensorData<float>();
        std::vector<Box> part = decodeOutput(data, shape, strides[i], score_threshold);
        boxes.insert(boxes.end(), part.begin(), part.end());
    }
    std::vector<int> keep = nms(boxes, nms_threshold, topk);
    const int count = std::min(static_cast<int>(keep.size()), impl_->result_buffer_count);
    const float sx = static_cast<float>(width) / static_cast<float>(kModelWidth);
    const float sy = static_cast<float>(height) / static_cast<float>(kModelHeight);
    for (int i = 0; i < count; ++i) {
        const Box& box = boxes[keep[static_cast<size_t>(i)]];
        float* out = impl_->result_buffer + static_cast<size_t>(i) * 5;
        out[0] = box.x1 * sx;
        out[1] = box.y1 * sy;
        out[2] = (box.x2 - box.x1) * sx;
        out[3] = (box.y2 - box.y1) * sy;
        out[4] = box.score;
    }
    return count;
}

}  // namespace persondet
