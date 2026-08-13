#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cctype>
#include <dirent.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

// Requires libcurl and nlohmann/json:
//   sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
#include <curl/curl.h>
#include <nlohmann/json.hpp>

// Public API endpoint. Change this to your own deployment if needed.
static const std::string kBaseURL = "https://www.w-agent.cn/api";

// Registered-user API Key. It is sent as: Authorization: Bearer <api_key>.
// Change this value before building/running the demo.
static const std::string kAPIKey = "gak_your_api_key";

// A sequence is a directory of cropped person images belonging to one track.
// Change this value, or pass a sequence directory as the first command-line argument.
static const std::string kSeqDir = "./images";
static constexpr double kSamePersonThreshold = 0.7;

struct HTTPResponse {
  long status = 0;
  std::string body;
};

static size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
}

std::string lowerExt(const std::string& name);

// Send an authenticated JSON request to the registered-user API.
HTTPResponse requestJSON(const std::string& method, const std::string& path, const nlohmann::json* payload, bool allowPending = false) {
  CURL* curl = curl_easy_init();
  if (!curl) {
    throw std::runtime_error("curl_easy_init failed");
  }

  std::string body;
  std::string url = kBaseURL + path;
  std::string payloadText = payload ? payload->dump() : "";
  struct curl_slist* headers = nullptr;
  std::string apiKey = kAPIKey;
  if (apiKey.empty() || apiKey == "gak_your_api_key") {
    throw std::runtime_error("edit kAPIKey in sequence_demo/main.cpp before running this demo");
  }
  std::string auth = "Authorization: Bearer " + apiKey;
  headers = curl_slist_append(headers, "Accept: application/json");
  headers = curl_slist_append(headers, auth.c_str());
  if (payload) {
    headers = curl_slist_append(headers, "Content-Type: application/json");
  }

  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
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
  if (code != CURLE_OK) {
    throw std::runtime_error(curl_easy_strerror(code));
  }
  if (status >= 400 && !(allowPending && status == 409)) {
    std::ostringstream oss;
    oss << "HTTP " << status << " " << method << " " << path << "\n" << body;
    throw std::runtime_error(oss.str());
  }
  return {status, body};
}

std::string uploadTokenFromUploads(const nlohmann::json& uploads) {
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

void uploadFramesBatch(const std::string& taskID, const std::string& uploadToken, const std::vector<std::string>& frames) {
  CURL* curl = curl_easy_init();
  if (!curl) {
    throw std::runtime_error("curl_easy_init failed");
  }
  std::string url = kBaseURL + "/v1/sequences/" + taskID + "/uploads/batch";
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
  if (code != CURLE_OK) {
    throw std::runtime_error(curl_easy_strerror(code));
  }
  if (status >= 400) {
    std::ostringstream oss;
    oss << "HTTP " << status << " POST /v1/sequences/" << taskID << "/uploads/batch\n" << responseBody;
    throw std::runtime_error(oss.str());
  }
}

// Return the lower-case extension of a filename, including the dot.
std::string lowerExt(const std::string& name) {
  size_t pos = name.find_last_of('.');
  if (pos == std::string::npos) {
    return "";
  }
  std::string ext = name.substr(pos);
  std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return ext;
}

// Read image files from a sequence directory in deterministic name order.
std::vector<std::string> collectFrames(const std::string& dir) {
  std::vector<std::string> frames;
  DIR* handle = opendir(dir.c_str());
  if (!handle) {
    throw std::runtime_error("failed to open directory " + dir);
  }
  while (dirent* entry = readdir(handle)) {
    std::string name = entry->d_name;
    if (name == "." || name == "..") {
      continue;
    }
    std::string ext = lowerExt(name);
    if (ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".bmp" || ext == ".webp") {
      frames.push_back(dir + "/" + name);
    }
  }
  closedir(handle);
  std::sort(frames.begin(), frames.end());
  return frames;
}

std::string sequenceDir(int argc, char** argv) {
  if (argc > 1 && argv[1] && *argv[1]) return argv[1];
  return kSeqDir;
}

int main(int argc, char** argv) {
  try {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    // Step 1: read all sequence frames from the local directory.
    std::string seqDir = sequenceDir(argc, argv);
    std::vector<std::string> frames = collectFrames(seqDir);
  if (frames.empty()) {
    throw std::runtime_error("no image frames under " + seqDir);
  }

  // Step 2: create a sequence task. The server returns one upload slot per
  // frame. Each upload slot contains an object_key for the parse request.
  nlohmann::json createPayload = {{"frame_count", frames.size()}};
  nlohmann::json created = nlohmann::json::parse(requestJSON("POST", "/v1/sequences", &createPayload).body);
  std::string taskID = created.at("task_id").get<std::string>();
  const nlohmann::json& uploads = created.at("uploads");
  if (uploads.size() != frames.size()) {
    throw std::runtime_error("upload count mismatch");
  }

  // Step 3: upload all frames once and build the frames payload for parsing.
  // The parse API needs the index/object_key pairs returned by the server.
  uploadFramesBatch(taskID, uploadTokenFromUploads(uploads), frames);
  nlohmann::json parseFrames = nlohmann::json::array();
  for (size_t i = 0; i < frames.size(); ++i) {
    const nlohmann::json& slot = uploads.at(i);
    parseFrames.push_back({{"index", slot.at("index")}, {"object_key", slot.at("object_key")}});
  }
  nlohmann::json parsePayload = {{"frames", parseFrames}};

  // Step 4: start synchronous gait sequence parsing. Registered users are billed
  // from their account balance by the server.
  nlohmann::json parsed = nlohmann::json::parse(requestJSON("POST", "/v1/sequences/" + taskID + "/parse", &parsePayload).body);

  // Step 5: fetch the stored result list. This is useful if the caller wants to
  // retrieve the result again later by task_id.
  nlohmann::json result = nlohmann::json::parse(requestJSON("GET", "/v1/sequences/" + taskID + "/result", nullptr).body);
  nlohmann::json first = nlohmann::json::object();
  if (result.contains("sequences") && result["sequences"].is_array() && !result["sequences"].empty()) {
    first = result["sequences"][0];
  }

  // Feature vectors are usually 512-dimensional. face_feature may be empty
  // when no usable face is found in the sequence.
  printf("task_id=%s\n", taskID.c_str());
  printf("status=%s\n", parsed.value("status", "").c_str());
  printf("sequence_count=%d\n", parsed.value("sequence_count", 0));
  printf("sequence_id=%s\n", first.value("sequence_id", "").c_str());
  printf("frame_count=%d\n", first.value("frame_count", 0));
  printf("gait_feature_dim=%zu\n", first.value("gait_feature", nlohmann::json::array()).size());
  printf("reid_feature_dim=%zu\n", first.value("reid_feature", nlohmann::json::array()).size());
  printf("face_feature_dim=%zu\n", first.value("face_feature", nlohmann::json::array()).size());
  printf("same_person_threshold=%.2f\n", kSamePersonThreshold);
    curl_global_cleanup();
    return 0;
  } catch (const std::exception& ex) {
    curl_global_cleanup();
    std::cerr << ex.what() << "\n";
    return 1;
  }
}
