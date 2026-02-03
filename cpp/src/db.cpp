#include "db.hpp"
#include <libpq-fe.h>
#include <stdexcept>
#include <cstring>

namespace stashy {

Db::Db(const std::string& conninfo) : conninfo_(conninfo) {}

Db::~Db() { disconnect(); }

bool Db::connect() {
  if (conn_) return true;
  conn_ = PQconnectdb(conninfo_.c_str());
  if (PQstatus(conn_) != CONNECTION_OK) {
    disconnect();
    return false;
  }
  return true;
}

void Db::disconnect() {
  if (conn_) {
    PQfinish(static_cast<PGconn*>(conn_));
    conn_ = nullptr;
  }
}

std::vector<UrlRow> Db::claim_pending(const std::string& worker_id, int batch_size) {
  std::vector<UrlRow> out;
  PGconn* c = static_cast<PGconn*>(conn_);
  if (!c) return out;
  const char* params[] = { worker_id.c_str(), std::to_string(batch_size).c_str() };
  PGresult* res = PQexecParams(c,
    "SELECT id, url FROM claim_pending_urls($1::text, $2::int)",
    2, nullptr, params, nullptr, nullptr, 0);
  if (PQresultStatus(res) != PGRES_TUPLES_OK) {
    PQclear(res);
    return out;
  }
  int n = PQntuples(res);
  for (int i = 0; i < n; i++) {
    UrlRow row;
    row.id = std::stoll(PQgetvalue(res, i, 0));
    row.url = PQgetvalue(res, i, 1);
    out.push_back(std::move(row));
  }
  PQclear(res);
  return out;
}

void Db::mark_done(int64_t url_id) {
  PGconn* c = static_cast<PGconn*>(conn_);
  if (!c) return;
  std::string id_str = std::to_string(url_id);
  const char* params[] = { id_str.c_str() };
  PGresult* res = PQexecParams(c,
    "UPDATE url_queue SET status = 'done', claimed_at = NULL, claimed_by = NULL WHERE id = $1::bigint",
    1, nullptr, params, nullptr, nullptr, 0);
  PQclear(res);
}

void Db::mark_failed(int64_t url_id, const std::string& error) {
  PGconn* c = static_cast<PGconn*>(conn_);
  if (!c) return;
  std::string id_str = std::to_string(url_id);
  std::string err_trunc = error.size() > 4096 ? error.substr(0, 4096) : error;
  const char* params[] = { id_str.c_str(), err_trunc.c_str() };
  PGresult* res = PQexecParams(c,
    R"(UPDATE url_queue SET status = CASE WHEN retries + 1 >= max_retries THEN 'failed' ELSE 'pending' END,
       retries = retries + 1, claimed_at = NULL, claimed_by = NULL, error = $2, updated_at = now() WHERE id = $1::bigint)",
    2, nullptr, params, nullptr, nullptr, 0);
  PQclear(res);
}

bool Db::insert_raw_page(int64_t url_id, const std::string& url,
                         const std::string& html, int status_code,
                         const std::string& content_type) {
  PGconn* c = static_cast<PGconn*>(conn_);
  if (!c) return false;
  std::string id_str = std::to_string(url_id);
  const char* params[] = { id_str.c_str(), url.c_str(), html.c_str(),
                           std::to_string(status_code).c_str(), content_type.c_str() };
  PGresult* res = PQexecParams(c,
    R"(INSERT INTO raw_pages (url_id, url, html, status_code, content_type)
       VALUES ($1::bigint, $2::text, $3::text, $4::int, $5::text)
       ON CONFLICT (url_id) DO UPDATE SET html = $3, status_code = $4, content_type = $5, fetched_at = now())",
    5, nullptr, params, nullptr, nullptr, 0);
  bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK || PQresultStatus(res) == PGRES_TUPLES_OK);
  PQclear(res);
  return ok;
}

}  // namespace stashy
