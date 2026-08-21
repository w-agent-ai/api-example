#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <curl/curl.h>

// Official API base URL. Keep /api when using the hosted service.
static const std::string kBaseURL = "https://www.w-agent.cn/api";

// Replace this placeholder with an active registered-user API Key.
static const std::string kAPIKey = "gak_your_api_key";

static size_t writeCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* output = static_cast<std::string*>(userdata);
  output->append(ptr, size * nmemb);
  return size * nmemb;
}

static std::string base64Encode(const std::vector<unsigned char>& data) {
  static const char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string output;
  output.reserve(((data.size() + 2) / 3) * 4);
  for (size_t i = 0; i < data.size(); i += 3) {
    unsigned int value = static_cast<unsigned int>(data[i]) << 16;
    if (i + 1 < data.size()) value |= static_cast<unsigned int>(data[i + 1]) << 8;
    if (i + 2 < data.size()) value |= static_cast<unsigned int>(data[i + 2]);
    output.push_back(table[(value >> 18) & 63]);
    output.push_back(table[(value >> 12) & 63]);
    output.push_back(i + 1 < data.size() ? table[(value >> 6) & 63] : '=');
    output.push_back(i + 2 < data.size() ? table[value & 63] : '=');
  }
  return output;
}

static std::string jsonEscape(const std::string& value) {
  std::string output;
  for (char ch : value) {
    if (ch == '\\' || ch == '"') output.push_back('\\');
    output.push_back(ch);
  }
  return output;
}

// Sends one image and prompt to Object Search. The server charges the API Key
// account after a successful search.
static std::string searchObject(const std::string& imageBase64, const std::string& prompt) {
  if (kAPIKey.empty() || kAPIKey == "gak_your_api_key") {
    throw std::runtime_error("edit kAPIKey in main.cpp before running");
  }
  CURL* curl = curl_easy_init();
  if (!curl) throw std::runtime_error("curl_easy_init failed");
  const std::string payload = "{\"image_base64\":\"" + imageBase64 + "\",\"prompt\":\"" + jsonEscape(prompt) + "\"}";
  const std::string url = kBaseURL + "/v1/object-search";
  std::string response;
  struct curl_slist* headers = nullptr;
  const std::string authorization = "Authorization: Bearer " + kAPIKey;
  headers = curl_slist_append(headers, "Accept: application/json");
  headers = curl_slist_append(headers, "Content-Type: application/json");
  headers = curl_slist_append(headers, authorization.c_str());
  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload.c_str());
  curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, payload.size());
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 120L);
  const CURLcode code = curl_easy_perform(curl);
  long status = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  if (code != CURLE_OK) throw std::runtime_error(curl_easy_strerror(code));
  if (status >= 400) {
    std::ostringstream message;
    message << "HTTP " << status << "\n" << response;
    throw std::runtime_error(message.str());
  }
  return response;
}

int main(int argc, char** argv) {
  try {
    if (argc < 3) {
      std::cerr << "Usage: " << argv[0] << " /path/to/image.jpg \"prompt\"\n";
      return 2;
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) throw std::runtime_error("failed to open image");
    const std::vector<unsigned char> image((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    if (image.empty()) throw std::runtime_error("image is empty");
    std::cout << searchObject(base64Encode(image), argv[2]) << "\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "error: " << error.what() << "\n";
    return 1;
  }
}
