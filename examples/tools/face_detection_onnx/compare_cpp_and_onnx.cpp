#include <algorithm>
#include <cmath>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

#include <opencv2/opencv.hpp>

#include "facedet_onnx.h"
#include "facedetectcnn.h"

namespace {

struct LegacyFace {
  float score = 0.0f;
  cv::Rect box;
  std::vector<cv::Point2f> landmarks;
};

std::vector<LegacyFace> detectLegacy(const cv::Mat& bgr) {
  std::vector<unsigned char> buffer(FACEDETECTION_RESULT_BUFFER_SIZE);
  int* raw = facedetect_cnn(buffer.data(), const_cast<unsigned char*>(bgr.ptr<unsigned char>(0)), bgr.cols, bgr.rows, static_cast<int>(bgr.step));
  int count = raw ? *raw : 0;
  std::vector<LegacyFace> faces;
  for (int i = 0; i < count; ++i) {
    short* p = reinterpret_cast<short*>(raw + 1) + FACEDETECTION_RESULT_STRIDE_SHORTS * i;
    LegacyFace face;
    face.score = static_cast<float>(p[0]) / 100.0f;
    face.box = cv::Rect(p[1], p[2], p[3], p[4]);
    for (int point = 0; point < 5; ++point) {
      face.landmarks.emplace_back(static_cast<float>(p[5 + point * 2]), static_cast<float>(p[6 + point * 2]));
    }
    faces.push_back(std::move(face));
  }
  return faces;
}

float pointError(const std::vector<cv::Point2f>& a, const std::vector<cv::Point2f>& b) {
  if (a.size() != b.size() || a.empty()) return -1.0f;
  float sum = 0.0f;
  for (size_t i = 0; i < a.size(); ++i) {
    sum += cv::norm(a[i] - b[i]);
  }
  return sum / static_cast<float>(a.size());
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "Usage: " << argv[0] << " /path/to/face.jpg [...]\n";
    return 2;
  }
  try {
    FaceDetectorONNX detector;
    int failures = 0;
    for (int arg = 1; arg < argc; ++arg) {
      const std::string image_path = argv[arg];
      cv::Mat bgr = cv::imread(image_path);
      if (bgr.empty()) {
        std::cerr << image_path << ": failed to read image\n";
        failures += 1;
        continue;
      }
      std::vector<LegacyFace> legacy = detectLegacy(bgr);
      std::vector<FaceCandidate> onnx = detector.detect(bgr);
      std::cout << image_path << "\n";
      std::cout << "  legacy_count=" << legacy.size() << " onnx_count=" << onnx.size() << "\n";
      if (legacy.empty() || onnx.empty()) {
        failures += legacy.size() == onnx.size() ? 0 : 1;
        continue;
      }
      const LegacyFace& a = legacy[0];
      const FaceCandidate& b = onnx[0];
      const float dx = static_cast<float>(std::abs(a.box.x - b.box.x));
      const float dy = static_cast<float>(std::abs(a.box.y - b.box.y));
      const float dw = static_cast<float>(std::abs(a.box.width - b.box.width));
      const float dh = static_cast<float>(std::abs(a.box.height - b.box.height));
      const float lm_err = pointError(a.landmarks, b.landmarks);
      std::cout << "  legacy_score=" << a.score << " box=[" << a.box.x << "," << a.box.y << "," << a.box.width << "," << a.box.height << "]\n";
      std::cout << "  onnx_score=" << b.score << " box=[" << b.box.x << "," << b.box.y << "," << b.box.width << "," << b.box.height << "]\n";
      std::cout << "  abs_box_error=[" << dx << "," << dy << "," << dw << "," << dh << "] landmark_mean_error=" << lm_err << "\n";
      if (dx > 2.0f || dy > 2.0f || dw > 3.0f || dh > 3.0f || lm_err > 3.0f) {
        failures += 1;
      }
    }
    return failures == 0 ? 0 : 1;
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }
}
