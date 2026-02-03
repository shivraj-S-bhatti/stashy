#include "fetcher.hpp"
#include <curl/curl.h>
#include <sstream>
#include <string>
#include <cstring>

namespace stashy {

namespace {

size_t write_cb(char* ptr, size_t size, size_t nmemb, void* userdata) {
  size_t total = size * nmemb;
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, total);
  return total;
}

}  // namespace

std::optional<FetchResult> fetch_url(const std::string& url,
                                       int timeout_sec,
                                       const std::string& user_agent) {
  CURL* curl = curl_easy_init();
  if (!curl) return std::nullopt;

  std::string body;
  long status_code = 0;
  char* ct = nullptr;

  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
  curl_easy_setopt(curl, CURLOPT_MAXREDIRS, 5L);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, static_cast<long>(timeout_sec));
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
  curl_easy_setopt(curl, CURLOPT_USERAGENT, user_agent.c_str());
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);

  CURLcode res = curl_easy_perform(curl);
  if (res != CURLE_OK) {
    FetchResult fr;
    fr.error = curl_easy_strerror(res);
    curl_easy_cleanup(curl);
    return fr;
  }
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status_code);
  curl_easy_getinfo(curl, CURLINFO_CONTENT_TYPE, &ct);

  FetchResult fr;
  fr.html = std::move(body);
  fr.status_code = static_cast<int>(status_code);
  if (ct) {
    fr.content_type = ct;
    const char* semicolon = std::strchr(ct, ';');
    if (semicolon)
      fr.content_type = std::string(ct, semicolon - ct);
  }
  curl_easy_cleanup(curl);
  return fr;
}

}  // namespace stashy
