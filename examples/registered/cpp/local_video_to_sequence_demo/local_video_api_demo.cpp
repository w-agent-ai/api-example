#include <algorithm>
#include <cstdlib>
#include <cctype>
#include <dirent.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

namespace fs = std::filesystem;

// Change these values before building/running the demo.
// kBaseURL is the public API endpoint. Keep /api at the end on the official site.
static const std::string kBaseURL = "https://www.w-agent.cn/api";

// Registered-user API Key. Local video detection is free; billing starts when
// generated sequence folders are uploaded and parsed by the API.
static const std::string kAPIKey = "gak_your_api_key";

// Optional default video path. You can also pass the video path as argv[1].
static const std::string kVideoPath = "input.mp4";

struct HTTPResponse {
  long status = 0;
  std::string body;
};

static size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
}

static std::string shellQuote(const std::string& value) {
  std::string out = "'";
  for (char ch : value) {
    if (ch == '\'') out += "'\\''";
    else out += ch;
  }
  out += "'";
  return out;
}

static std::string lowerExt(const std::string& name) {
  size_t pos = name.find_last_of('.');
  if (pos == std::string::npos) return "";
  std::string ext = name.substr(pos);
  std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return ext;
}

static std::vector<std::string> collectFrames(const fs::path& dir) {
  std::vector<std::string> frames;
  for (const auto& item : fs::directory_iterator(dir)) {
    if (!item.is_regular_file()) continue;
    std::string ext = lowerExt(item.path().string());
    if (ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".bmp" || ext == ".webp") {
      frames.push_back(item.path().string());
    }
  }
  std::sort(frames.begin(), frames.end());
  return frames;
}

static std::vector<fs::path> collectSequenceDirs(const fs::path& root) {
  std::vector<fs::path> dirs;
  if (!fs::is_directory(root)) return dirs;
  for (const auto& item : fs::directory_iterator(root)) {
    if (item.is_directory()) dirs.push_back(item.path());
  }
  std::sort(dirs.begin(), dirs.end());
  return dirs;
}

// Send an authenticated JSON request to the registered-user API.
static HTTPResponse requestJSON(const std::string& method, const std::string& path, const nlohmann::json* payload) {
  if (kAPIKey.empty() || kAPIKey == "gak_your_api_key") {
    throw std::runtime_error("edit kAPIKey in local_video_api_demo.cpp before running this demo");
  }
  CURL* curl = curl_easy_init();
  if (!curl) throw std::runtime_error("curl_easy_init failed");

  std::string body;
  std::string payloadText = payload ? payload->dump() : "";
  struct curl_slist* headers = nullptr;
  std::string auth = "Authorization: Bearer " + kAPIKey;
  headers = curl_slist_append(headers, "Accept: application/json");
  headers = curl_slist_append(headers, auth.c_str());
  if (payload) headers = curl_slist_append(headers, "Content-Type: application/json");

  curl_easy_setopt(curl, CURLOPT_URL, (kBaseURL + path).c_str());
  curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, method.c_str());
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 600L);
  if (payload) {
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payloadText.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, payloadText.size());
  }

  CURLcode code = curl_easy_perform(curl);
  long status = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  if (code != CURLE_OK) throw std::runtime_error(curl_easy_strerror(code));
  if (status >= 400) {
    std::ostringstream oss;
    oss << "HTTP " << status << " " << method << " " << path << "\n" << body;
    throw std::runtime_error(oss.str());
  }
  return {status, body};
}

// Extract the one-time upload token from the first upload_url returned by
// POST /v1/sequences.
static std::string uploadTokenFromUploads(const nlohmann::json& uploads) {
  if (uploads.empty()) throw std::runtime_error("create response has no upload slots");
  std::string uploadURL = uploads.at(0).at("upload_url").get<std::string>();
  std::string needle = "token=";
  size_t pos = uploadURL.find(needle);
  if (pos == std::string::npos) throw std::runtime_error("upload_url has no token");
  std::string token = uploadURL.substr(pos + needle.size());
  size_t amp = token.find('&');
  if (amp != std::string::npos) token = token.substr(0, amp);
  if (token.empty()) throw std::runtime_error("upload_url has empty token");
  return token;
}

// Upload all frames for one tracked person in a single multipart/form-data
// request. The server maps files to upload slots by multipart order.
static void uploadFramesBatch(const std::string& taskID, const std::string& uploadToken, const std::vector<std::string>& frames) {
  CURL* curl = curl_easy_init();
  if (!curl) throw std::runtime_error("curl_easy_init failed");
  std::string auth = "Authorization: Bearer " + kAPIKey;
  struct curl_slist* headers = curl_slist_append(nullptr, auth.c_str());
  curl_mime* form = curl_mime_init(curl);
  curl_mimepart* part = curl_mime_addpart(form);
  curl_mime_name(part, "upload_token");
  curl_mime_data(part, uploadToken.c_str(), CURL_ZERO_TERMINATED);
  for (size_t i = 0; i < frames.size(); ++i) {
    char name[32];
    std::snprintf(name, sizeof(name), "%06zu.jpg", i);
    part = curl_mime_addpart(form);
    curl_mime_name(part, "frames");
    curl_mime_filedata(part, frames.at(i).c_str());
    curl_mime_filename(part, name);
    curl_mime_type(part, "image/jpeg");
  }
  std::string responseBody;
  std::string url = kBaseURL + "/v1/sequences/" + taskID + "/uploads/batch";
  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_MIMEPOST, form);
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &responseBody);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 600L);

  CURLcode code = curl_easy_perform(curl);
  long status = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_mime_free(form);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  if (code != CURLE_OK) throw std::runtime_error(curl_easy_strerror(code));
  if (status >= 400) {
    std::ostringstream oss;
    oss << "HTTP " << status << " POST /v1/sequences/" << taskID << "/uploads/batch\n" << responseBody;
    throw std::runtime_error(oss.str());
  }
}

static nlohmann::json uploadSequence(const fs::path& seqDir) {
  std::vector<std::string> frames = collectFrames(seqDir);
  if (frames.empty()) throw std::runtime_error("no image frames under " + seqDir.string());

  // Create a sequence task, upload all local track frames, then call /parse.
  nlohmann::json createPayload = {{"frame_count", frames.size()}};
  nlohmann::json created = nlohmann::json::parse(requestJSON("POST", "/v1/sequences", &createPayload).body);
  const nlohmann::json& uploads = created.at("uploads");
  if (uploads.size() != frames.size()) throw std::runtime_error("upload count mismatch");

  std::string taskID = created.at("task_id").get<std::string>();
  uploadFramesBatch(taskID, uploadTokenFromUploads(uploads), frames);
  nlohmann::json parseFrames = nlohmann::json::array();
  for (size_t i = 0; i < frames.size(); ++i) {
    const nlohmann::json& slot = uploads.at(i);
    parseFrames.push_back({{"index", slot.at("index")}, {"object_key", slot.at("object_key")}});
  }

  nlohmann::json payload = {{"frames", parseFrames}};
  return nlohmann::json::parse(requestJSON("POST", "/v1/sequences/" + taskID + "/parse", &payload).body);
}

int main(int argc, char** argv) {
  try {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    std::string videoPath = argc > 1 ? argv[1] : kVideoPath;
    if (videoPath.empty() || videoPath == "input.mp4") {
      throw std::runtime_error("edit kVideoPath in local_video_api_demo.cpp or pass a video path argument");
    }

    fs::path video(videoPath);
    fs::path sequenceRoot = video.stem().string() + "_gait_sequences";

    // Run the local ONNX detector/tracker first. This creates one image folder
    // per person track under <video_stem>_gait_sequences.
    std::string extractor = "./local_video_sequence_extractor";
    if (fs::exists("./build/local_video_sequence_extractor")) extractor = "./build/local_video_sequence_extractor";
    std::string command = shellQuote(extractor) + " " + shellQuote(videoPath);
    int rc = std::system(command.c_str());
    if (rc != 0) throw std::runtime_error("local video sequence extraction failed");

    std::vector<fs::path> seqDirs = collectSequenceDirs(sequenceRoot);
    if (seqDirs.empty()) throw std::runtime_error("no sequence folders generated under " + sequenceRoot.string());

    // Upload and parse each generated track independently.
    std::cout << "sequence_count=" << seqDirs.size() << "\n";
    for (size_t i = 0; i < seqDirs.size(); ++i) {
      std::cout << "uploading_sequence=" << seqDirs[i].string() << "\n";
      nlohmann::json result = uploadSequence(seqDirs[i]);
      std::cout << result.dump(2) << "\n";
    }
    curl_global_cleanup();
    return 0;
  } catch (const std::exception& ex) {
    curl_global_cleanup();
    std::cerr << ex.what() << "\n";
    return 1;
  }
}
