#include "facedet_onnx.h"

#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

#if defined(__linux__)
#include <limits.h>
#include <unistd.h>
#endif

namespace {

constexpr const char* kModelName = "face_detect.onnx";
constexpr float kConfidenceThreshold = 0.2f;
constexpr float kNMSThreshold = 0.45f;
constexpr int kTopK = 1000;
constexpr int kKeepTopK = 512;

struct DecodedFace {
  float score = 0.0f;
  float x1 = 0.0f;
  float y1 = 0.0f;
  float x2 = 0.0f;
  float y2 = 0.0f;
  std::array<float, 10> landmarks{};
};

float sigmoid(float x) {
  x = std::max(-88.3762626647949f, std::min(88.3762626647949f, x));
  return 1.0f / (1.0f + std::exp(-x));
}

float iou(const DecodedFace& a, const DecodedFace& b) {
  const float xx1 = std::max(a.x1, b.x1);
  const float yy1 = std::max(a.y1, b.y1);
  const float xx2 = std::min(a.x2, b.x2);
  const float yy2 = std::min(a.y2, b.y2);
  const float inter = std::max(0.0f, xx2 - xx1) * std::max(0.0f, yy2 - yy1);
  const float area_a = std::max(0.0f, a.x2 - a.x1) * std::max(0.0f, a.y2 - a.y1);
  const float area_b = std::max(0.0f, b.x2 - b.x1) * std::max(0.0f, b.y2 - b.y1);
  const float denom = area_a + area_b - inter;
  return denom > 0.0f ? inter / denom : 0.0f;
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

std::filesystem::path findModelPath(const std::string& requested) {
  if (!requested.empty()) {
    std::filesystem::path p(requested);
    if (std::filesystem::exists(p)) return p;
  }
  if (const char* env = std::getenv("W_AGENT_FACEDET_ONNX")) {
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
  throw std::runtime_error("face detector ONNX model not found: " + std::string(kModelName));
}

void preprocessBGR(const cv::Mat& bgr, std::vector<float>& out, int& rows, int& cols) {
  if (bgr.empty() || bgr.channels() != 3) {
    throw std::runtime_error("face detector input must be a non-empty BGR image");
  }
  const int height = bgr.rows;
  const int width = bgr.cols;
  rows = ((height - 1) / 32 + 1) * 16;
  cols = ((width - 1) / 32 + 1) * 16;
  out.assign(static_cast<size_t>(32) * rows * cols, 0.0f);
  for (int r = 0; r < rows; ++r) {
    for (int c = 0; c < cols; ++c) {
      for (int fy = -1; fy <= 1; ++fy) {
        const int src_y = r * 2 + fy;
        if (src_y < 0 || src_y >= height) continue;
        const unsigned char* row_ptr = bgr.ptr<unsigned char>(src_y);
        for (int fx = -1; fx <= 1; ++fx) {
          const int src_x = c * 2 + fx;
          if (src_x < 0 || src_x >= width) continue;
          const int offset = (fy + 1) * 3 + fx + 1;
          const unsigned char* p = row_ptr + src_x * 3;
          for (int ch = 0; ch < 3; ++ch) {
            out[static_cast<size_t>(offset * 3 + ch) * rows * cols + static_cast<size_t>(r) * cols + c] =
                static_cast<float>(p[ch]);
          }
        }
      }
    }
  }
}

void decodeLevel(
    const float* cls,
    const float* reg,
    const float* kps,
    const float* obj,
    const std::vector<int64_t>& shape,
    int stride,
    std::vector<DecodedFace>& out) {
  if (!cls || !reg || !kps || !obj || shape.size() != 4) return;
  const int h = static_cast<int>(shape[2]);
  const int w = static_cast<int>(shape[3]);
  const size_t plane = static_cast<size_t>(h) * w;
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const size_t idx = static_cast<size_t>(y) * w + x;
      const float score = std::sqrt(sigmoid(cls[idx]) * sigmoid(obj[idx]));
      if (score < kConfidenceThreshold) continue;
      const float prior_x = static_cast<float>(x * stride);
      const float prior_y = static_cast<float>(y * stride);
      const float cx = reg[idx] * stride + prior_x;
      const float cy = reg[plane + idx] * stride + prior_y;
      const float bw = std::exp(reg[2 * plane + idx]) * stride;
      const float bh = std::exp(reg[3 * plane + idx]) * stride;
      DecodedFace face;
      face.score = score;
      face.x1 = cx - bw * 0.5f;
      face.y1 = cy - bh * 0.5f;
      face.x2 = cx + bw * 0.5f;
      face.y2 = cy + bh * 0.5f;
      for (int point = 0; point < 5; ++point) {
        face.landmarks[point * 2] = kps[static_cast<size_t>(point * 2) * plane + idx] * stride + prior_x;
        face.landmarks[point * 2 + 1] = kps[static_cast<size_t>(point * 2 + 1) * plane + idx] * stride + prior_y;
      }
      out.push_back(face);
    }
  }
}

std::vector<DecodedFace> runNMS(std::vector<DecodedFace> faces) {
  std::stable_sort(faces.begin(), faces.end(), [](const DecodedFace& a, const DecodedFace& b) {
    return a.score > b.score;
  });
  if (kTopK > -1 && static_cast<int>(faces.size()) > kTopK) faces.resize(kTopK);

  std::vector<DecodedFace> kept;
  for (const auto& face : faces) {
    bool keep = true;
    for (const auto& prev : kept) {
      if (iou(face, prev) > kNMSThreshold) {
        keep = false;
        break;
      }
    }
    if (keep) kept.push_back(face);
    if (kKeepTopK > -1 && static_cast<int>(kept.size()) >= kKeepTopK) break;
  }
  return kept;
}

}  // namespace

struct FaceDetectorONNX::Impl {
  explicit Impl(const std::string& requested_model_path)
      : model_path(findModelPath(requested_model_path)),
        env(ORT_LOGGING_LEVEL_WARNING, "w-agent-facedet") {
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
    std::cerr << "[facedet] onnxruntime cpu model=" << model_path << std::endl;
  }

  std::filesystem::path model_path;
  Ort::Env env;
  std::unique_ptr<Ort::Session> session;
  std::string input_name;
  std::vector<std::string> output_names;
  std::vector<const char*> output_name_ptrs;
};

FaceDetectorONNX::FaceDetectorONNX(const std::string& model_path)
    : impl_(std::make_unique<Impl>(model_path)) {}

FaceDetectorONNX::~FaceDetectorONNX() = default;

std::vector<FaceCandidate> FaceDetectorONNX::detect(const cv::Mat& bgr) const {
  if (!impl_ || !impl_->session) return {};
  std::vector<float> tensor;
  int rows = 0;
  int cols = 0;
  preprocessBGR(bgr, tensor, rows, cols);

  std::array<int64_t, 4> input_shape = {1, 32, rows, cols};
  Ort::MemoryInfo memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
  Ort::Value input = Ort::Value::CreateTensor<float>(
      memory_info,
      tensor.data(),
      tensor.size(),
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

  std::vector<DecodedFace> decoded;
  for (size_t level = 0; level < 3; ++level) {
    const size_t base = level * 4;
    if (outputs.size() <= base + 3) break;
    const auto shape = outputs[base].GetTensorTypeAndShapeInfo().GetShape();
    decodeLevel(
        outputs[base].GetTensorData<float>(),
        outputs[base + 1].GetTensorData<float>(),
        outputs[base + 2].GetTensorData<float>(),
        outputs[base + 3].GetTensorData<float>(),
        shape,
        level == 0 ? 8 : (level == 1 ? 16 : 32),
        decoded);
  }

  decoded = runNMS(std::move(decoded));
  std::vector<FaceCandidate> faces;
  faces.reserve(decoded.size());
  for (const auto& item : decoded) {
    FaceCandidate face;
    face.score = item.score;
    face.box = cv::Rect(
        static_cast<int>(item.x1),
        static_cast<int>(item.y1),
        static_cast<int>(item.x2 - item.x1),
        static_cast<int>(item.y2 - item.y1));
    for (int point = 0; point < 5; ++point) {
      face.landmarks.emplace_back(item.landmarks[point * 2], item.landmarks[point * 2 + 1]);
    }
    faces.push_back(std::move(face));
  }
  return faces;
}

FaceCandidate detectBestFaceONNX(const cv::Mat& bgr, FaceDetectorONNX& detector) {
  std::vector<FaceCandidate> faces = detector.detect(bgr);
  if (faces.empty()) {
    throw std::runtime_error("no face detected");
  }
  return *std::max_element(faces.begin(), faces.end(), [](const FaceCandidate& a, const FaceCandidate& b) {
    return a.score * std::max(1, a.box.area()) < b.score * std::max(1, b.box.area());
  });
}

cv::Mat alignFace(const cv::Mat& bgr, const FaceCandidate& face) {
  if (face.landmarks.size() < 2) {
    throw std::runtime_error("face landmarks missing");
  }
  cv::Point2f leftEye = face.landmarks[0];
  cv::Point2f rightEye = face.landmarks[1];
  cv::Point2f eyeCenter((leftEye.x + rightEye.x) * 0.5f, (leftEye.y + rightEye.y) * 0.5f);
  double angle = std::atan2(rightEye.y - leftEye.y, rightEye.x - leftEye.x) * 180.0 / CV_PI;
  double eyeDistance = cv::norm(rightEye - leftEye);
  double targetEyeDistance = 48.0;
  double scale = targetEyeDistance / std::max(eyeDistance, 1.0);
  cv::Mat rot = cv::getRotationMatrix2D(eyeCenter, angle, scale);
  rot.at<double>(0, 2) += 56.0 - eyeCenter.x;
  rot.at<double>(1, 2) += 44.0 - eyeCenter.y;
  cv::Mat aligned;
  cv::warpAffine(bgr, aligned, rot, cv::Size(112, 112), cv::INTER_LINEAR, cv::BORDER_REPLICATE);
  return aligned;
}
