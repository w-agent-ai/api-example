#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cctype>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

// Requires libcurl and nlohmann/json:
//   sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
#include <curl/curl.h>
#include <nlohmann/json.hpp>

// Public API endpoint. Change this to your own deployment if needed.
static const std::string kBaseURL = "http://116.198.210.0:3005";

// Registered-user API Key. It is sent as: Authorization: Bearer <api_key>.
static const std::string kAPIKey = "";

// A video file is uploaded once, then parsed asynchronously by the server.
static const std::string kVideoPath = "../../../video/0000.avi";

struct HTTPResponse {
  long status = 0;
  std::string body;
};

static size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
}

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

std::string fileName(const std::string& path) {
  size_t pos = path.find_last_of("/\\");
  if (pos == std::string::npos) {
    return path;
  }
  return path.substr(pos + 1);
}

long fileSize(const std::string& filename) {
  std::ifstream input(filename, std::ios::binary | std::ios::ate);
  if (!input) {
    throw std::runtime_error("failed to open " + filename);
  }
  return static_cast<long>(input.tellg());
}

std::string contentTypeFor(const std::string& filename) {
  std::string ext = lowerExt(filename);
  if (ext == ".mp4") {
    return "video/mp4";
  }
  if (ext == ".avi") {
    return "video/x-msvideo";
  }
  if (ext == ".mov") {
    return "video/quicktime";
  }
  return "application/octet-stream";
}

static constexpr double kSamePersonThreshold = 0.7;

std::vector<double> numericVector(const nlohmann::json& item, const char* key) {
  std::vector<double> out;
  if (!item.contains(key) || !item[key].is_array()) return out;
  for (const auto& value : item[key]) {
    if (value.is_number()) out.push_back(value.get<double>());
  }
  return out;
}

double dotProduct(const std::vector<double>& left, const std::vector<double>& right) {
  size_t used = std::min(left.size(), right.size());
  double score = 0.0;
  for (size_t i = 0; i < used; ++i) score += left[i] * right[i];
  return score;
}

double fusedIdentitySimilarity(double faceSim, double gaitSim, double reidSim) {
  double result = std::max(gaitSim, 0.0);
  if (faceSim > 0.45)      result = std::max(gaitSim, 0.7);
  else if (faceSim > 0.35) result *= 1.1;
  else if (faceSim > 0.4)  result *= 1.1;
  else if (faceSim != 0 && faceSim < 0.1) result *= 0.9;
  if (reidSim > 0.8)       result *= 1.1;
  if (faceSim > 0.5)       result *= 1.1;
  if (faceSim > 0.6)       result *= 1.1;
  return std::min(result, 1.0);
}

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
  std::string apiKey = std::getenv("GAIT_REGISTERED_API_KEY") ? std::getenv("GAIT_REGISTERED_API_KEY") : kAPIKey;
  if (apiKey.empty()) {
    throw std::runtime_error("export GAIT_REGISTERED_API_KEY before running this demo");
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

// Upload the video to the upload_url returned by POST /v1/videos.
// Upload URLs are service-relative paths in this deployment.
void uploadFile(const std::string& uploadPath, const std::string& filename) {
  std::ifstream input(filename, std::ios::binary);
  if (!input) {
    throw std::runtime_error("failed to open " + filename);
  }
  std::string data((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());

  CURL* curl = curl_easy_init();
  if (!curl) {
    throw std::runtime_error("curl_easy_init failed");
  }
  std::string url = kBaseURL + uploadPath;
  std::string contentType = "Content-Type: " + contentTypeFor(filename);
  struct curl_slist* headers = curl_slist_append(nullptr, contentType.c_str());
  std::string responseBody;
  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_UPLOAD, 1L);
  curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "PUT");
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, data.data());
  curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, data.size());
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &responseBody);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 600L);

  CURLcode code = curl_easy_perform(curl);
  long status = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  if (code != CURLE_OK) {
    throw std::runtime_error(curl_easy_strerror(code));
  }
  if (status >= 400) {
    std::ostringstream oss;
    oss << "HTTP " << status << " PUT " << uploadPath << "\n" << responseBody;
    throw std::runtime_error(oss.str());
  }
}

int main() {
  try {
    curl_global_init(CURL_GLOBAL_DEFAULT);

    // Step 1: create a video task with filename, content type and file size.
    // The server returns an upload_url for the video binary.
    std::string name = fileName(kVideoPath);
    nlohmann::json createPayload = {
        {"filename", name},
        {"content_type", contentTypeFor(name)},
        {"size_bytes", fileSize(kVideoPath)},
    };
    nlohmann::json created = nlohmann::json::parse(requestJSON("POST", "/v1/videos", &createPayload).body);
    std::string taskID = created.at("task_id").get<std::string>();

    // Step 2: upload the whole video file, then notify the server that upload is
    // complete. Registered video parsing is asynchronous.
    uploadFile(created.at("upload_url").get<std::string>(), kVideoPath);
    nlohmann::json emptyPayload = nlohmann::json::object();
    requestJSON("POST", "/v1/videos/" + taskID + "/complete", &emptyPayload);

    // Step 3: poll until the worker finishes parsing. HTTP 409 means the result
    // is not ready yet.
    nlohmann::json result;
    for (int i = 0; i < 900; ++i) {
      HTTPResponse resp = requestJSON("GET", "/v1/videos/" + taskID + "/result", nullptr, true);
      if (resp.status == 200) {
        result = nlohmann::json::parse(resp.body);
        break;
      }
      std::this_thread::sleep_for(std::chrono::seconds(2));
    }
    if (result.is_null()) {
      throw std::runtime_error("timed out waiting for video result: " + taskID);
    }

    printf("video_task_id=%s\n", taskID.c_str());
    printf("video_status=%s\n", result.value("status", "").c_str());
    printf("sequence_count=%d\n", result.value("sequence_count", 0));
    printf("total_sequence_frames=%d\n", result.value("total_sequence_frames", 0));
    if (result.contains("sequences") && result["sequences"].is_array() && !result["sequences"].empty()) {
      const nlohmann::json& first = result["sequences"][0];
      printf("first_sequence_id=%s\n", first.value("sequence_id", "").c_str());
      printf("first_gait_feature_dim=%zu\n", first.value("gait_feature", nlohmann::json::array()).size());
      printf("first_reid_feature_dim=%zu\n", first.value("reid_feature", nlohmann::json::array()).size());
      printf("first_face_feature_dim=%zu\n", first.value("face_feature", nlohmann::json::array()).size());
    }
    if (result.contains("sequences") && result["sequences"].is_array() && result["sequences"].size() >= 2) {
      const nlohmann::json& left = result["sequences"][0];
      const nlohmann::json& right = result["sequences"][1];
      double gaitSim = dotProduct(numericVector(left, "gait_feature"), numericVector(right, "gait_feature"));
      double reidSim = dotProduct(numericVector(left, "reid_feature"), numericVector(right, "reid_feature"));
      double faceSim = dotProduct(numericVector(left, "face_feature"), numericVector(right, "face_feature"));
      double fusedSim = fusedIdentitySimilarity(faceSim, gaitSim, reidSim);
      printf("same_person_threshold=%.2f\n", kSamePersonThreshold);
      printf("seq0_seq1_gait_similarity=%.6f\n", gaitSim);
      printf("seq0_seq1_reid_similarity=%.6f\n", reidSim);
      printf("seq0_seq1_face_similarity=%.6f\n", faceSim);
      printf("seq0_seq1_fused_similarity=%.6f\n", fusedSim);
      printf("seq0_seq1_same_person_likely=%s\n", fusedSim > kSamePersonThreshold ? "true" : "false");
    }

    curl_global_cleanup();
    return 0;
  } catch (const std::exception& ex) {
    curl_global_cleanup();
    std::cerr << ex.what() << "\n";
    return 1;
  }
}
