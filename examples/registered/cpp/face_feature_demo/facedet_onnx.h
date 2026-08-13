#pragma once

#include <opencv2/opencv.hpp>

#include <memory>
#include <string>
#include <vector>

struct FaceCandidate {
  float score = 0.0f;
  cv::Rect box;
  std::vector<cv::Point2f> landmarks;
};

class FaceDetectorONNX {
 public:
  explicit FaceDetectorONNX(const std::string& model_path = "");
  ~FaceDetectorONNX();

  std::vector<FaceCandidate> detect(const cv::Mat& bgr) const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

FaceCandidate detectBestFaceONNX(const cv::Mat& bgr, FaceDetectorONNX& detector);
cv::Mat alignFace(const cv::Mat& bgr, const FaceCandidate& face);
