#include "persondet.h"

#include <chrono>
#include <cstdio>
#include <opencv2/opencv.hpp>

static int round_to_multiple(float value, int multiple) {
    int v = (int)std::round(value / multiple) * multiple;
    return std::max(multiple, v);
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: %s image.jpg [output.jpg] [resize_width] [score_threshold]\n", argv[0]);
        std::printf("example: %s image.jpg result.jpg 640 0.30\n", argv[0]);
        std::printf("resize_width defaults to 640. score_threshold defaults to 0.30.\n");
        return 1;
    }

    const char* output_path = argc >= 3 ? argv[2] : "image_detect_result.jpg";
    int resize_width = argc >= 4 ? std::atoi(argv[3]) : 640;
    float score_threshold = argc >= 5 ? (float)std::atof(argv[4]) : 0.30f;
    cv::Mat bgr = cv::imread(argv[1], cv::IMREAD_COLOR);
    if (bgr.empty()) {
        std::printf("failed to read image: %s\n", argv[1]);
        return 1;
    }

    cv::Mat resized;
    if (resize_width > 0) {
        int resize_height = round_to_multiple((float)bgr.rows * resize_width / bgr.cols, 32);
        cv::resize(bgr, resized, cv::Size(resize_width, resize_height), 0, 0, cv::INTER_LINEAR);
    } else {
        resized = bgr;
    }

    const int max_results = 1024;
    std::vector<float> results((size_t)max_results * 5);
    persondet::Detector detector(results.data(), max_results);

    auto t0 = std::chrono::high_resolution_clock::now();
    int count = detector.detect_bgr(resized.data, resized.cols, resized.rows, (int)resized.step, score_threshold);
    auto t1 = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    std::printf("input=%dx%d score_thresh=%.4f detections=%d time=%.2fms\n", resized.cols, resized.rows, score_threshold, count, ms);
    for (int i = 0; i < count; ++i) {
        const float* d = results.data() + (size_t)i * 5;
        int x = (int)d[0];
        int y = (int)d[1];
        int w = (int)d[2];
        int h = (int)d[3];
        float score = d[4];
        std::printf("%.4f %d %d %d %d\n", score, x, y, w, h);
        cv::rectangle(resized, cv::Rect(x, y, w, h), cv::Scalar(0, 255, 0), 2);
        char text[32];
        std::snprintf(text, sizeof(text), "%.2f", score);
        cv::putText(resized, text, cv::Point(x, std::max(0, y - 4)), cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
    }

    cv::imwrite(output_path, resized);
    std::printf("output=%s\n", output_path);
    return 0;
}
