#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include <opencv2/opencv.hpp>
#include <opencv2/dnn.hpp>

namespace {

constexpr int kInputSize = 640;
constexpr float kScoreThreshold = 0.30f;
constexpr float kNmsThreshold = 0.45f;
constexpr int kMaxDet = 100;

struct LetterboxResult {
    cv::Mat blob;
    float scale = 1.0f;
    int pad_x = 0;
    int pad_y = 0;
};

struct Detection {
    float score = 0.0f;
    float x0 = 0.0f;
    float y0 = 0.0f;
    float x1 = 0.0f;
    float y1 = 0.0f;
};

LetterboxResult letterbox_rgb(const cv::Mat& bgr) {
    int w = bgr.cols;
    int h = bgr.rows;
    float scale = std::min((float)kInputSize / std::max(w, 1), (float)kInputSize / std::max(h, 1));
    int new_w = (int)std::round(w * scale);
    int new_h = (int)std::round(h * scale);
    cv::Mat resized;
    cv::resize(bgr, resized, cv::Size(new_w, new_h), 0, 0, cv::INTER_LINEAR);
    cv::Mat canvas(kInputSize, kInputSize, CV_8UC3, cv::Scalar(0, 0, 0));
    int pad_x = (kInputSize - new_w) / 2;
    int pad_y = (kInputSize - new_h) / 2;
    resized.copyTo(canvas(cv::Rect(pad_x, pad_y, new_w, new_h)));
    cv::Mat rgb;
    cv::cvtColor(canvas, rgb, cv::COLOR_BGR2RGB);
    cv::Mat blob = cv::dnn::blobFromImage(rgb, 1.0 / 255.0, cv::Size(kInputSize, kInputSize), cv::Scalar(), false, false, CV_32F);
    return {blob, scale, pad_x, pad_y};
}

float iou(const Detection& a, const Detection& b) {
    float x0 = std::max(a.x0, b.x0);
    float y0 = std::max(a.y0, b.y0);
    float x1 = std::min(a.x1, b.x1);
    float y1 = std::min(a.y1, b.y1);
    float iw = std::max(0.0f, x1 - x0);
    float ih = std::max(0.0f, y1 - y0);
    float inter = iw * ih;
    float aa = std::max(0.0f, a.x1 - a.x0) * std::max(0.0f, a.y1 - a.y0);
    float ab = std::max(0.0f, b.x1 - b.x0) * std::max(0.0f, b.y1 - b.y0);
    return inter / std::max(aa + ab - inter, 1e-6f);
}

std::vector<Detection> nms(std::vector<Detection> dets) {
    std::sort(dets.begin(), dets.end(), [](const Detection& a, const Detection& b) { return a.score > b.score; });
    std::vector<Detection> kept;
    std::vector<char> removed(dets.size(), 0);
    for (size_t i = 0; i < dets.size(); ++i) {
        if (removed[i]) continue;
        kept.push_back(dets[i]);
        if ((int)kept.size() >= kMaxDet) break;
        for (size_t j = i + 1; j < dets.size(); ++j) {
            if (!removed[j] && iou(dets[i], dets[j]) > kNmsThreshold) removed[j] = 1;
        }
    }
    return kept;
}

std::vector<Detection> decode(const cv::Mat& output, int image_w, int image_h, float scale, int pad_x, int pad_y) {
    if (output.dims != 3) {
        throw std::runtime_error("unexpected ONNX output dims");
    }
    int c = output.size[1];
    int n = output.size[2];
    if (c != 5) {
        throw std::runtime_error("expected output shape [1,5,N]");
    }
    const float* p = (const float*)output.data;
    std::vector<Detection> dets;
    for (int i = 0; i < n; ++i) {
        float score = p[4 * n + i];
        if (score < kScoreThreshold) continue;
        float cx = p[0 * n + i];
        float cy = p[1 * n + i];
        float bw = p[2 * n + i];
        float bh = p[3 * n + i];
        Detection d;
        d.score = score;
        d.x0 = (cx - bw * 0.5f - pad_x) / scale;
        d.y0 = (cy - bh * 0.5f - pad_y) / scale;
        d.x1 = (cx + bw * 0.5f - pad_x) / scale;
        d.y1 = (cy + bh * 0.5f - pad_y) / scale;
        d.x0 = std::max(0.0f, std::min(d.x0, (float)(image_w - 1)));
        d.y0 = std::max(0.0f, std::min(d.y0, (float)(image_h - 1)));
        d.x1 = std::max(0.0f, std::min(d.x1, (float)(image_w - 1)));
        d.y1 = std::max(0.0f, std::min(d.y1, (float)(image_h - 1)));
        if (d.x1 > d.x0 && d.y1 > d.y0) dets.push_back(d);
    }
    return nms(std::move(dets));
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: %s image.jpg [output.jpg] [model.onnx]\n", argv[0]);
        return 1;
    }
    std::string image_path = argv[1];
    std::string output_path = argc >= 3 ? argv[2] : "onnx_det.jpg";
    std::string model_path = argc >= 4 ? argv[3] : "onnx/gait_detect_dynamic_slim.onnx";

    cv::Mat image = cv::imread(image_path, cv::IMREAD_COLOR);
    if (image.empty()) {
        std::printf("failed to read image: %s\n", image_path.c_str());
        return 1;
    }

    std::vector<Detection> dets;
    double ms = 0.0;
    try {
        cv::dnn::Net net = cv::dnn::readNetFromONNX(model_path);
        LetterboxResult input = letterbox_rgb(image);
        auto t0 = std::chrono::high_resolution_clock::now();
        net.setInput(input.blob);
        cv::Mat output = net.forward();
        dets = decode(output, image.cols, image.rows, input.scale, input.pad_x, input.pad_y);
        auto t1 = std::chrono::high_resolution_clock::now();
        ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    } catch (const cv::Exception& e) {
        std::fprintf(stderr, "failed to run ONNX with OpenCV DNN %s\n", CV_VERSION);
        std::fprintf(stderr, "%s\n", e.what());
        std::fprintf(stderr, "This model needs a newer OpenCV DNN build on some systems. The Python ONNX demo works with the current Python cv2 wheel.\n");
        return 2;
    }

    cv::Mat drawn = image.clone();
    for (const auto& d : dets) {
        int x = (int)std::round(d.x0);
        int y = (int)std::round(d.y0);
        int w = (int)std::round(d.x1 - d.x0);
        int h = (int)std::round(d.y1 - d.y0);
        std::printf("%.4f %d %d %d %d\n", d.score, x, y, w, h);
        cv::rectangle(drawn, cv::Rect(x, y, w, h), cv::Scalar(0, 0, 255), 2);
        char text[32];
        std::snprintf(text, sizeof(text), "%.2f", d.score);
        cv::putText(drawn, text, cv::Point(x, std::max(0, y - 4)), cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 0, 255), 1);
    }
    cv::imwrite(output_path, drawn);
    std::printf("detections=%zu time=%.2fms output=%s\n", dets.size(), ms, output_path.c_str());
    return 0;
}
