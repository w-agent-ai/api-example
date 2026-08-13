#include <algorithm>
#include <cctype>
#include <cstdio>
#include <dirent.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

// Public API endpoint. Keep /api at the end when using the official website.
static const std::string kBaseURL = "https://www.w-agent.cn/api";

// Registered-user API Key. It is sent as: Authorization: Bearer <api_key>.
// Change this value before building/running the demo.
static const std::string kAPIKey = "gak_your_api_key";

// A sequence is a directory of cropped person images belonging to one track.
// Change this value, or pass a sequence directory as the first command-line argument.
static const std::string kSeqDir = "./images";

struct HTTPResponse {
  long status = 0;
  std::string body;
};

static size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
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

static std::vector<std::string> collectFrames(const std::string& dir) {
  std::vector<std::string> frames;
  DIR* handle = opendir(dir.c_str());
  if (!handle) throw std::runtime_error("failed to open directory " + dir);
  while (dirent* entry = readdir(handle)) {
    std::string name = entry->d_name;
    if (name == "." || name == "..") continue;
    std::string ext = lowerExt(name);
    if (ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".bmp" || ext == ".webp") {
      frames.push_back(dir + "/" + name);
    }
  }
  closedir(handle);
  std::sort(frames.begin(), frames.end());
  return frames;
}

static HTTPResponse requestJSON(const std::string& method, const std::string& path, const nlohmann::json* payload) {
  if (kAPIKey.empty() || kAPIKey == "gak_your_api_key") {
    throw std::runtime_error("edit kAPIKey in gait_pose_demo/main.cpp before running this demo");
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

// Upload all sequence frames in one multipart/form-data request. The server
// uses the order of the "frames" parts to match the upload slots.
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

int main(int argc, char** argv) {
  try {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    // Step 1: read all sequence frames from the local directory.
    std::string seqDir = argc > 1 ? argv[1] : kSeqDir;
    std::vector<std::string> frames = collectFrames(seqDir);
    if (frames.empty()) throw std::runtime_error("no image frames under " + seqDir);

    // Step 2: create a sequence task. The server returns one upload slot per frame.
    nlohmann::json createPayload = {{"frame_count", frames.size()}};
    nlohmann::json created = nlohmann::json::parse(requestJSON("POST", "/v1/sequences", &createPayload).body);
    std::string taskID = created.at("task_id").get<std::string>();
    const nlohmann::json& uploads = created.at("uploads");
    if (uploads.size() != frames.size()) throw std::runtime_error("upload count mismatch");

    // Step 3: upload all frames once and build the frames payload for keypoint extraction.
    uploadFramesBatch(taskID, uploadTokenFromUploads(uploads), frames);
    nlohmann::json parseFrames = nlohmann::json::array();
    for (size_t i = 0; i < frames.size(); ++i) {
      const nlohmann::json& slot = uploads.at(i);
      parseFrames.push_back({{"index", slot.at("index")}, {"object_key", slot.at("object_key")}});
    }

    // Step 4: call the standalone human 2D/3D keypoint API. Registered users
    // are billed from their account balance by the server.
    nlohmann::json payload = {{"frames", parseFrames}};
    nlohmann::json pose = nlohmann::json::parse(requestJSON("POST", "/v1/sequences/" + taskID + "/gait-pose", &payload).body);
    nlohmann::json result = pose.value("result", nlohmann::json::object());

    printf("task_id=%s\n", taskID.c_str());
    printf("status=%s\n", pose.value("status", "").c_str());
    printf("sequence_id=%s\n", result.value("sequence_id", "").c_str());
    printf("frame_count=%d\n", result.value("frame_count", 0));
    printf("pose2d_frames=%zu\n", result.value("pose_2ds", nlohmann::json::array()).size());
    printf("pose3d_frames=%zu\n", result.value("pose_3ds", nlohmann::json::array()).size());
    curl_global_cleanup();
    return 0;
  } catch (const std::exception& ex) {
    curl_global_cleanup();
    std::cerr << ex.what() << "\n";
    return 1;
  }
}
