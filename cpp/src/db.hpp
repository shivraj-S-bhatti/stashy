#pragma once

#include <string>
#include <vector>
#include <optional>
#include <cstdint>

namespace stashy {

struct UrlRow {
  int64_t id;
  std::string url;
};

class Db {
public:
  explicit Db(const std::string& conninfo);
  ~Db();

  bool connect();
  void disconnect();

  // Claim up to batch_size pending URLs for worker_id. Returns claimed rows.
  std::vector<UrlRow> claim_pending(const std::string& worker_id, int batch_size);
  void mark_done(int64_t url_id);
  void mark_failed(int64_t url_id, const std::string& error);
  bool insert_raw_page(int64_t url_id, const std::string& url,
                       const std::string& html, int status_code,
                       const std::string& content_type);

private:
  std::string conninfo_;
  void* conn_ = nullptr;  // PGconn*
};

}  // namespace stashy
