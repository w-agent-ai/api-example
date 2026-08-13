#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <curl/curl.h>
#include <opencv2/opencv.hpp>

// Public API endpoint. Keep /api at the end when using the official website.
static const std::string kBaseURL = "https://www.w-agent.cn/api";

// Registered-user API Key. It is sent as: Authorization: Bearer <api_key>.
// Change this value before building/running the demo.
static const std::string kAPIKey = "gak_your_api_key";

static size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
}

static std::string base64Encode(const unsigned char* data, size_t len) {
  static const char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;
  out.reserve(((len + 2) / 3) * 4);
  for (size_t i = 0; i < len; i += 3) {
    unsigned int v = static_cast<unsigned int>(data[i]) << 16;
    if (i + 1 < len) v |= static_cast<unsigned int>(data[i + 1]) << 8;
    if (i + 2 < len) v |= static_cast<unsigned int>(data[i + 2]);
    out.push_back(table[(v >> 18) & 63]);
    out.push_back(table[(v >> 12) & 63]);
    out.push_back(i + 1 < len ? table[(v >> 6) & 63] : '=');
    out.push_back(i + 2 < len ? table[v & 63] : '=');
  }
  return out;
}

// Send one cropped person image to the registered-user ReID API. Billing happens
// on the server side after the request is accepted.
static std::string postReIDFeature(const std::string& imageBase64) {
  if (kAPIKey.empty() || kAPIKey == "gak_your_api_key") {
    throw std::runtime_error("edit kAPIKey in main.cpp before running");
  }
  CURL* curl = curl_easy_init();
  if (!curl) throw std::runtime_error("curl_easy_init failed");
  std::string response;
  std::string payload = std::string("{\"image_base64\":\"") + imageBase64 + "\"}";
  std::string url = kBaseURL + "/v1/features/reid";
  struct curl_slist* headers = nullptr;
  std::string auth = "Authorization: Bearer " + kAPIKey;
  headers = curl_slist_append(headers, "Accept: application/json");
  headers = curl_slist_append(headers, "Content-Type: application/json");
  headers = curl_slist_append(headers, auth.c_str());
  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload.c_str());
  curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, payload.size());
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 120L);
  CURLcode code = curl_easy_perform(curl);
  long status = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  if (code != CURLE_OK) throw std::runtime_error(curl_easy_strerror(code));
  if (status >= 400) {
    std::ostringstream oss;
    oss << "HTTP " << status << "\n" << response;
    throw std::runtime_error(oss.str());
  }
  return response;
}

int main(int argc, char** argv) {
  try {
    if (argc < 2) {
      std::cerr << "Usage: " << argv[0] << " /path/to/image.jpg\n";
      return 2;
    }
    cv::Mat bgr = cv::imread(argv[1]);
    if (bgr.empty()) throw std::runtime_error("failed to read image");

    // The ReID API expects a single person crop. If your original image contains
    // multiple people, detect and crop the target person before calling this demo.
    std::vector<unsigned char> jpeg;
    cv::imencode(".jpg", bgr, jpeg, {cv::IMWRITE_JPEG_QUALITY, 92});

    // The HTTP API accepts raw base64 without a data:image/... prefix.
    std::cout << postReIDFeature(base64Encode(jpeg.data(), jpeg.size())) << "\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }
}
