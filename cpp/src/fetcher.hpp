#pragma once

#include <string>
#include <optional>
#include <cstdint>

namespace stashy {

struct FetchResult {
  std::string html;
  int status_code = 0;
  std::string content_type;
  std::string error;
};

// Synchronous HTTP GET. Returns nullopt on failure; otherwise FetchResult.
std::optional<FetchResult> fetch_url(const std::string& url,
                                       int timeout_sec = 30,
                                       const std::string& user_agent = "Stashy/1.0");

}  // namespace stashy
