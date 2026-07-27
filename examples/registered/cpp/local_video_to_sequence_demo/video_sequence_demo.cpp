#include "persondet.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include <opencv2/opencv.hpp>

namespace fs = std::filesystem;

namespace {

static std::string stem_of(const std::string& path);

struct Options {
    std::string video_path;
    std::string output_dir;

    // Fixed extraction parameters. Change them here if the default behavior
    // needs to be adjusted.
    float score_threshold = 0.35f;
    float nms_threshold = 0.50f;
    int resize_width = 640;
    int default_jump = 2;
    int jump = 2;
    float min_effective_fps = 10.0f;
    float max_effective_fps = 20.0f;
    int max_age = 25;
    int min_frames = 20;
    int max_frames = 120;
    int min_box_width = 64;
    int min_box_height = 128;
    float match_iou = 0.30f;
    float enlarge = 0.20f;
    float moving_pair_change_threshold = 0.70f;
    float moving_scale_threshold = 0.30f;
    int crop_width = 0;
    int crop_height = 0;
    bool save_full = false;
    int topk = 1000;
};

struct Detection {
    cv::Rect2f det_input;
    cv::Rect2f det_orig;
    float score = 0.0f;
};

struct Track {
    int id = 0;
    cv::Rect2f box;
    int last_frame = 0;
    int age = 0;
    int missed = 0;
    std::vector<int> sequence_ids;
};

struct SequenceFrame {
    int frame_id = 0;
    cv::Rect det_box;
    cv::Rect crop_box;
    float score = 0.0f;
    std::string crop_file;
    std::string full_file;
};

struct Sequence {
    int seq_id = 0;
    int track_id = 0;
    int frame_width = 0;
    int frame_height = 0;
    std::vector<SequenceFrame> frames;
};

static cv::Rect intersect_rect(const cv::Rect& a, const cv::Rect& b) {
    int x1 = std::max(a.x, b.x);
    int y1 = std::max(a.y, b.y);
    int x2 = std::min(a.x + a.width, b.x + b.width);
    int y2 = std::min(a.y + a.height, b.y + b.height);
    return cv::Rect(x1, y1, std::max(0, x2 - x1), std::max(0, y2 - y1));
}

static bool is_sequence_moving(
    int width,
    int height,
    const std::vector<cv::Rect>& rects,
    float pair_change_threshold,
    float scale_threshold) {
    int count = static_cast<int>(rects.size());
    if (count < 1) return false;

    int max_x = 0;
    int max_y = 0;
    int min_x = 999999;
    int min_y = 999999;
    int top_y = 999999;
    int bottom_y = 0;
    int total_width = 0;
    int total_height = 0;

    cv::Rect common = rects[0];
    for (const auto& r1 : rects) {
        if (r1.area() <= 0) continue;
        total_width += r1.width;
        total_height += r1.height;
        common = intersect_rect(r1, common);
        min_x = std::min(min_x, r1.x + r1.width / 2);
        max_x = std::max(max_x, r1.x + r1.width / 2);
        min_y = std::min(min_y, r1.y + r1.height / 2);
        max_y = std::max(max_y, r1.y + r1.height / 2);
        top_y = std::min(top_y, r1.y);
        bottom_y = std::max(bottom_y, r1.y + r1.height);

        for (const auto& r2 : rects) {
            if (r2.area() <= 0) continue;
            cv::Rect inter = intersect_rect(r1, r2);
            float change = 1.0f - std::min(
                static_cast<float>(inter.area()) / std::max(1, r1.area()),
                static_cast<float>(inter.area()) / std::max(1, r2.area()));
            if (change > pair_change_threshold) return true;
        }
    }

    if (total_width <= 0 || total_height <= 0) return false;
    int avg_width = total_width / count;
    int avg_height = total_height / count;
    if (avg_width <= 0 || avg_height <= 0) return false;

    if (common.width < avg_width * scale_threshold || common.height < avg_height * scale_threshold) {
        return true;
    }

    float scale_x = static_cast<float>(max_x - min_x) / avg_width;
    float scale_y = static_cast<float>(max_y - min_y) / avg_height;

    if (scale_y < 0.1f) {
        int tap = height / 20;
        if (top_y > tap && bottom_y < height - tap) return false;
    }
    if (scale_x < scale_threshold && scale_y < scale_threshold) return false;
    return true;
}

static void print_usage(const char* prog) {
    std::cerr << "usage: " << prog << " video.mp4\n";
}

static bool parse_args(int argc, char** argv, Options& opt) {
    if (argc != 2) return false;
    opt.video_path = argv[1];
    opt.output_dir = stem_of(opt.video_path) + "_gait_sequences";
    opt.jump = std::max(1, opt.jump);
    opt.max_age = std::max(1, opt.max_age);
    opt.min_frames = std::max(1, opt.min_frames);
    opt.max_frames = std::max(opt.min_frames, opt.max_frames);
    opt.resize_width = std::max(0, opt.resize_width);
    opt.enlarge = std::max(0.0f, opt.enlarge);
    return true;
}

static int round_to_multiple(float value, int multiple) {
    int v = static_cast<int>(std::round(value / multiple)) * multiple;
    return std::max(multiple, v);
}

static int choose_jump(double video_fps, const Options& opt) {
    int jump = std::max(1, opt.default_jump);
    if (video_fps <= 0.0 || !std::isfinite(video_fps)) return jump;

    while (jump > 1 && video_fps / jump < opt.min_effective_fps) {
        --jump;
    }
    while (video_fps / jump > opt.max_effective_fps) {
        ++jump;
    }
    return std::max(1, jump);
}

static cv::Rect clamp_rect(const cv::Rect& r, int width, int height) {
    int x1 = std::clamp(r.x, 0, std::max(0, width - 1));
    int y1 = std::clamp(r.y, 0, std::max(0, height - 1));
    int x2 = std::clamp(r.x + r.width, 0, width);
    int y2 = std::clamp(r.y + r.height, 0, height);
    return cv::Rect(x1, y1, std::max(0, x2 - x1), std::max(0, y2 - y1));
}

static cv::Rect enlarge_rect(const cv::Rect2f& box, float ratio, int width, int height) {
    float dw = box.width * ratio;
    float dh = box.height * ratio;
    cv::Rect r(
        static_cast<int>(std::floor(box.x - dw * 0.5f)),
        static_cast<int>(std::floor(box.y - dh * 0.5f)),
        static_cast<int>(std::ceil(box.width + dw)),
        static_cast<int>(std::ceil(box.height + dh)));
    return clamp_rect(r, width, height);
}

static float iou(const cv::Rect2f& a, const cv::Rect2f& b) {
    float x1 = std::max(a.x, b.x);
    float y1 = std::max(a.y, b.y);
    float x2 = std::min(a.x + a.width, b.x + b.width);
    float y2 = std::min(a.y + a.height, b.y + b.height);
    float iw = std::max(0.0f, x2 - x1);
    float ih = std::max(0.0f, y2 - y1);
    float inter = iw * ih;
    float uni = a.area() + b.area() - inter;
    return uni > 0.0f ? inter / uni : 0.0f;
}

static std::string stem_of(const std::string& path) {
    std::string stem = fs::path(path).stem().string();
    if (stem.empty()) stem = "video";
    for (char& ch : stem) {
        if (!(std::isalnum(static_cast<unsigned char>(ch)) || ch == '_' || ch == '-')) ch = '_';
    }
    return stem;
}

static std::string seq_dir_name(const std::string& video_stem, int seq_id, int track_id) {
    std::ostringstream oss;
    oss << video_stem
        << "_seq" << std::setw(6) << std::setfill('0') << seq_id
        << "_track" << std::setw(6) << std::setfill('0') << track_id;
    return oss.str();
}

static std::string frame_file_name(int frame_id) {
    std::ostringstream oss;
    oss << "frame_" << std::setw(6) << std::setfill('0') << frame_id << ".jpg";
    return oss.str();
}

class SequenceWriter {
public:
    SequenceWriter(const Options& opt, std::string video_stem)
        : opt_(opt), video_stem_(std::move(video_stem)) {
        fs::create_directories(opt_.output_dir);
    }

    void write_sequence(const Sequence& seq, const std::vector<cv::Mat>& crops, const std::vector<cv::Mat>& fulls) {
        if (static_cast<int>(seq.frames.size()) < opt_.min_frames) return;
        std::vector<cv::Rect> det_boxes;
        det_boxes.reserve(seq.frames.size());
        for (const auto& f : seq.frames) {
            det_boxes.push_back(f.det_box);
        }
        if (!is_sequence_moving(
                seq.frame_width,
                seq.frame_height,
                det_boxes,
                opt_.moving_pair_change_threshold,
                opt_.moving_scale_threshold)) {
            filtered_static_++;
            return;
        }

        fs::path dir = fs::path(opt_.output_dir) / seq_dir_name(video_stem_, seq.seq_id, seq.track_id);
        fs::create_directories(dir);

        std::ofstream meta(dir / "meta.txt");
        meta << "video=" << opt_.video_path << "\n";
        meta << "sequence_id=" << seq.seq_id << "\n";
        meta << "track_id=" << seq.track_id << "\n";
        meta << "frames=" << seq.frames.size() << "\n";
        meta << "columns=frame_id score det_x det_y det_w det_h crop_x crop_y crop_w crop_h crop_file full_file\n";

        for (size_t i = 0; i < seq.frames.size(); ++i) {
            const auto& f = seq.frames[i];
            fs::path crop_path = dir / f.crop_file;
            cv::Mat crop = crops[i];
            if (opt_.crop_width > 0 && opt_.crop_height > 0 && !crop.empty()) {
                cv::Mat resized;
                cv::resize(crop, resized, cv::Size(opt_.crop_width, opt_.crop_height), 0, 0, cv::INTER_LINEAR);
                crop = resized;
            }
            if (!crop.empty()) cv::imwrite(crop_path.string(), crop);

            if (opt_.save_full && i < fulls.size() && !fulls[i].empty()) {
                cv::imwrite((dir / f.full_file).string(), fulls[i]);
            }

            meta << f.frame_id << " " << f.score << " "
                 << f.det_box.x << " " << f.det_box.y << " " << f.det_box.width << " " << f.det_box.height << " "
                 << f.crop_box.x << " " << f.crop_box.y << " " << f.crop_box.width << " " << f.crop_box.height << " "
                 << f.crop_file << " " << f.full_file << "\n";
        }
        saved_++;
    }

    int saved() const { return saved_; }
    int filtered_static() const { return filtered_static_; }

private:
    const Options& opt_;
    std::string video_stem_;
    int saved_ = 0;
    int filtered_static_ = 0;
};

struct ActiveSequence {
    Sequence info;
    std::vector<cv::Mat> crops;
    std::vector<cv::Mat> fulls;
};

class GaitExtractor {
public:
    explicit GaitExtractor(const Options& opt)
        : opt_(opt), writer_(opt, stem_of(opt.video_path)), detector_(results_.data(), max_results_) {}

    int run() {
        cv::VideoCapture cap(opt_.video_path);
        if (!cap.isOpened()) {
            std::cerr << "failed to open video: " << opt_.video_path << "\n";
            return 1;
        }
        double video_fps = cap.get(cv::CAP_PROP_FPS);
        int jump = choose_jump(video_fps, opt_);
        double effective_fps = video_fps > 0.0 ? video_fps / jump : 0.0;
        std::cout << "video_fps=" << video_fps
                  << " jump=" << jump
                  << " effective_fps=" << effective_fps
                  << " output_dir=" << opt_.output_dir
                  << std::endl;

        cv::Mat frame;
        int frame_id = 0;
        int processed = 0;
        auto start = std::chrono::steady_clock::now();

        while (cap.read(frame)) {
            ++frame_id;
            if ((frame_id - 1) % jump != 0) continue;
            if (frame.empty()) continue;
            ++processed;

            std::vector<Detection> detections = detect(frame);
            update_tracks(detections, frame, frame_id);

            if (processed % 200 == 0) {
                auto now = std::chrono::steady_clock::now();
                double sec = std::chrono::duration<double>(now - start).count();
                std::cout << "processed=" << processed
                          << " frame=" << frame_id
                          << " active_tracks=" << tracks_.size()
                          << " saved_sequences=" << writer_.saved()
                          << " static_filtered=" << writer_.filtered_static()
                          << " fps=" << (sec > 0.0 ? processed / sec : 0.0)
                          << std::endl;
            }
        }

        finish_all();
        auto end = std::chrono::steady_clock::now();
        double sec = std::chrono::duration<double>(end - start).count();
        std::cout << "done processed=" << processed
                  << " saved_sequences=" << writer_.saved()
                  << " static_filtered=" << writer_.filtered_static()
                  << " time_sec=" << sec
                  << " fps=" << (sec > 0.0 ? processed / sec : 0.0)
                  << std::endl;
        return 0;
    }

private:
    std::vector<Detection> detect(const cv::Mat& frame) {
        cv::Mat input;
        float sx = 1.0f;
        float sy = 1.0f;
        if (opt_.resize_width > 0 && std::max(frame.cols, frame.rows) > opt_.resize_width) {
            int resized_w = frame.cols;
            int resized_h = frame.rows;
            if (frame.cols >= frame.rows) {
                resized_w = opt_.resize_width;
                resized_h = round_to_multiple(static_cast<float>(frame.rows) * resized_w / frame.cols, 32);
            } else {
                resized_h = opt_.resize_width;
                resized_w = round_to_multiple(static_cast<float>(frame.cols) * resized_h / frame.rows, 32);
            }
            cv::resize(frame, input, cv::Size(resized_w, resized_h), 0, 0, cv::INTER_LINEAR);
            sx = static_cast<float>(frame.cols) / input.cols;
            sy = static_cast<float>(frame.rows) / input.rows;
        } else {
            input = frame;
        }

        int count = detector_.detect_bgr(
            input.data,
            input.cols,
            input.rows,
            static_cast<int>(input.step),
            opt_.score_threshold,
            opt_.nms_threshold,
            opt_.topk);

        std::vector<Detection> detections;
        detections.reserve(count);
        for (int i = 0; i < count; ++i) {
            const float* d = results_.data() + static_cast<size_t>(i) * 5;
            Detection det;
            det.det_input = cv::Rect2f(d[0], d[1], d[2], d[3]);
            det.det_orig = cv::Rect2f(d[0] * sx, d[1] * sy, d[2] * sx, d[3] * sy);
            det.score = d[4];
            if (det.det_orig.width < opt_.min_box_width || det.det_orig.height < opt_.min_box_height) {
                continue;
            }
            detections.push_back(det);
        }
        return detections;
    }

    void update_tracks(const std::vector<Detection>& detections, const cv::Mat& frame, int frame_id) {
        std::vector<int> track_indices;
        std::vector<int> det_indices;
        greedy_match(detections, track_indices, det_indices);

        std::vector<bool> matched_track(tracks_.size(), false);
        std::vector<bool> matched_det(detections.size(), false);

        for (size_t i = 0; i < track_indices.size(); ++i) {
            int ti = track_indices[i];
            int di = det_indices[i];
            matched_track[ti] = true;
            matched_det[di] = true;
            Track& tr = tracks_[ti];
            tr.box = detections[di].det_orig;
            tr.last_frame = frame_id;
            tr.age++;
            tr.missed = 0;
            append_frame(tr, detections[di], frame, frame_id);
        }

        for (size_t i = 0; i < tracks_.size(); ++i) {
            if (!matched_track[i]) tracks_[i].missed++;
        }

        for (size_t di = 0; di < detections.size(); ++di) {
            if (matched_det[di]) continue;
            Track tr;
            tr.id = next_track_id_++;
            tr.box = detections[di].det_orig;
            tr.last_frame = frame_id;
            tr.age = 1;
            tr.missed = 0;
            tracks_.push_back(tr);
            append_frame(tracks_.back(), detections[di], frame, frame_id);
        }

        for (auto it = tracks_.begin(); it != tracks_.end();) {
            if (it->missed > opt_.max_age) {
                finish_track(*it);
                it = tracks_.erase(it);
            } else {
                ++it;
            }
        }
    }

    void greedy_match(
        const std::vector<Detection>& detections,
        std::vector<int>& track_indices,
        std::vector<int>& det_indices) const {
        struct Candidate {
            float score;
            int track;
            int det;
        };
        std::vector<Candidate> candidates;
        for (size_t ti = 0; ti < tracks_.size(); ++ti) {
            for (size_t di = 0; di < detections.size(); ++di) {
                float v = iou(tracks_[ti].box, detections[di].det_orig);
                if (v >= opt_.match_iou) candidates.push_back({v, static_cast<int>(ti), static_cast<int>(di)});
            }
        }
        std::sort(candidates.begin(), candidates.end(), [](const Candidate& a, const Candidate& b) {
            return a.score > b.score;
        });

        std::vector<bool> used_track(tracks_.size(), false);
        std::vector<bool> used_det(detections.size(), false);
        for (const auto& c : candidates) {
            if (used_track[c.track] || used_det[c.det]) continue;
            used_track[c.track] = true;
            used_det[c.det] = true;
            track_indices.push_back(c.track);
            det_indices.push_back(c.det);
        }
    }

    void append_frame(Track& tr, const Detection& det, const cv::Mat& frame, int frame_id) {
        int seq_id = 0;
        if (tr.sequence_ids.empty()) {
            seq_id = next_sequence_id_++;
            tr.sequence_ids.push_back(seq_id);
            ActiveSequence seq;
            seq.info.seq_id = seq_id;
            seq.info.track_id = tr.id;
            seq.info.frame_width = frame.cols;
            seq.info.frame_height = frame.rows;
            active_sequences_[seq_id] = std::move(seq);
        } else {
            seq_id = tr.sequence_ids.back();
        }

        ActiveSequence& seq = active_sequences_[seq_id];
        if (static_cast<int>(seq.info.frames.size()) >= opt_.max_frames) {
            finish_sequence(seq_id);
            seq_id = next_sequence_id_++;
            tr.sequence_ids.push_back(seq_id);
            ActiveSequence next;
            next.info.seq_id = seq_id;
            next.info.track_id = tr.id;
            next.info.frame_width = frame.cols;
            next.info.frame_height = frame.rows;
            active_sequences_[seq_id] = std::move(next);
        }

        ActiveSequence& current = active_sequences_[seq_id];
        cv::Rect det_box = clamp_rect(cv::Rect(
            static_cast<int>(std::round(det.det_orig.x)),
            static_cast<int>(std::round(det.det_orig.y)),
            static_cast<int>(std::round(det.det_orig.width)),
            static_cast<int>(std::round(det.det_orig.height))),
            frame.cols,
            frame.rows);
        cv::Rect crop_box = enlarge_rect(det.det_orig, opt_.enlarge, frame.cols, frame.rows);
        if (det_box.area() <= 0 || crop_box.area() <= 0) return;

        SequenceFrame sf;
        sf.frame_id = frame_id;
        sf.det_box = det_box;
        sf.crop_box = crop_box;
        sf.score = det.score;
        sf.crop_file = frame_file_name(frame_id);
        if (opt_.save_full) {
            std::ostringstream oss;
            oss << "full_" << std::setw(6) << std::setfill('0') << frame_id << ".jpg";
            sf.full_file = oss.str();
        }

        current.info.frames.push_back(sf);
        current.crops.push_back(frame(crop_box).clone());
        if (opt_.save_full) {
            cv::Mat full = frame.clone();
            cv::rectangle(full, det_box, cv::Scalar(0, 255, 0), 2);
            current.fulls.push_back(std::move(full));
        }
    }

    void finish_track(const Track& tr) {
        for (int seq_id : tr.sequence_ids) finish_sequence(seq_id);
    }

    void finish_sequence(int seq_id) {
        auto it = active_sequences_.find(seq_id);
        if (it == active_sequences_.end()) return;
        writer_.write_sequence(it->second.info, it->second.crops, it->second.fulls);
        active_sequences_.erase(it);
    }

    void finish_all() {
        std::vector<int> ids;
        ids.reserve(tracks_.size());
        for (const auto& tr : tracks_) {
            for (int seq_id : tr.sequence_ids) ids.push_back(seq_id);
        }
        for (int seq_id : ids) finish_sequence(seq_id);
        tracks_.clear();

        ids.clear();
        for (const auto& kv : active_sequences_) ids.push_back(kv.first);
        for (int seq_id : ids) finish_sequence(seq_id);
    }

    const Options& opt_;
    SequenceWriter writer_;
    static constexpr int max_results_ = 2048;
    std::vector<float> results_ = std::vector<float>(static_cast<size_t>(max_results_) * 5);
    persondet::Detector detector_;
    std::vector<Track> tracks_;
    std::map<int, ActiveSequence> active_sequences_;
    int next_track_id_ = 1;
    int next_sequence_id_ = 1;
};

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    if (!parse_args(argc, argv, opt)) {
        print_usage(argv[0]);
        return 1;
    }
    GaitExtractor extractor(opt);
    return extractor.run();
}
