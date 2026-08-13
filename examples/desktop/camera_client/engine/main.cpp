#include <chrono>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include <opencv2/opencv.hpp>

namespace fs = std::filesystem;

struct Options {
    std::string source_id;
    std::string type;
    std::string video;
    std::string rtsp;
    std::string output_dir;
    int emit_every = 30;
};

static std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
        case '\\': out << "\\\\"; break;
        case '"': out << "\\\""; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default: out << ch; break;
        }
    }
    return out.str();
}

static void emit(const std::string& line) {
    std::cout << line << std::endl;
}

static void emit_error(const Options& opt, const std::string& message) {
    emit("{\"type\":\"error\",\"source_id\":\"" + json_escape(opt.source_id) + "\",\"message\":\"" + json_escape(message) + "\"}");
}

static bool parse_args(int argc, char** argv, Options& opt) {
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) return "";
            return argv[++i];
        };
        if (key == "--source-id") opt.source_id = next();
        else if (key == "--type") opt.type = next();
        else if (key == "--video") opt.video = next();
        else if (key == "--rtsp") opt.rtsp = next();
        else if (key == "--output-dir") opt.output_dir = next();
        else if (key == "--emit-every") opt.emit_every = std::max(1, std::stoi(next()));
        else return false;
    }
    if (opt.source_id.empty() || opt.type.empty() || opt.output_dir.empty()) return false;
    if (opt.type == "video" && opt.video.empty()) return false;
    if (opt.type == "camera" && opt.rtsp.empty()) return false;
    return true;
}

int main(int argc, char** argv) {
    Options opt;
    if (!parse_args(argc, argv, opt)) {
        std::cerr << "usage: w-agent-local-engine --source-id ID --type video --video file.mp4 --output-dir DIR\n"
                  << "   or: w-agent-local-engine --source-id ID --type camera --rtsp rtsp://... --output-dir DIR\n";
        return 2;
    }

    fs::create_directories(opt.output_dir);
    std::string input = opt.type == "camera" ? opt.rtsp : opt.video;
    cv::VideoCapture cap(input);
    if (!cap.isOpened()) {
        emit_error(opt, "failed to open source: " + input);
        return 1;
    }

    double total = cap.get(cv::CAP_PROP_FRAME_COUNT);
    auto start = std::chrono::steady_clock::now();
    int processed = 0;
    cv::Mat frame;

    emit("{\"type\":\"ready\",\"source_id\":\"" + json_escape(opt.source_id) + "\"}");
    while (cap.read(frame)) {
        if (frame.empty()) continue;
        ++processed;

        // TODO(Windows agent): integrate persondet.cpp tracking and emit:
        // {"type":"sequence","source_id":"...","sequence_id":"...","sequence_dir":"...","frame_paths":["..."]}
        // after writing one tracked-person crop sequence.
        //
        // TODO(Windows agent): encode each capture clip to H.264/MP4, resized to
        // <= 720p, optionally with detection boxes, and emit capture events when
        // a clip is available.

        if (processed % opt.emit_every == 0) {
            auto now = std::chrono::steady_clock::now();
            double sec = std::chrono::duration<double>(now - start).count();
            double fps = sec > 0 ? processed / sec : 0;
            std::cout << "{\"type\":\"progress\",\"source_id\":\"" << json_escape(opt.source_id)
                      << "\",\"processed\":" << processed
                      << ",\"total\":" << static_cast<int>(total)
                      << ",\"fps\":" << fps << "}" << std::endl;
        }
    }

    emit("{\"type\":\"done\",\"source_id\":\"" + json_escape(opt.source_id) + "\"}");
    return 0;
}
