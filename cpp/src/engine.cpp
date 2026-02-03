#include "engine.hpp"
#include <iostream>
#include <chrono>

namespace stashy {

Engine::Engine(std::string conninfo, std::string worker_id, int concurrency, int batch_size)
  : conninfo_(std::move(conninfo))
  , worker_id_(std::move(worker_id))
  , concurrency_(concurrency > 0 ? concurrency : 4)
  , batch_size_(batch_size > 0 ? batch_size : 20)
{}

Engine::~Engine() { stop(); }

void Engine::stop() {
  running_ = false;
  for (auto& t : threads_)
    if (t.joinable()) t.join();
  threads_.clear();
}

void Engine::worker_thread(int index) {
  Db db(conninfo_);
  if (!db.connect()) {
    std::cerr << "Worker " << index << ": DB connect failed\n";
    return;
  }
  std::string my_id = worker_id_ + "-" + std::to_string(index);
  while (running_) {
    auto rows = db.claim_pending(my_id, batch_size_);
    if (rows.empty()) {
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      continue;
    }
    for (const auto& row : rows) {
      if (!running_) break;
      auto result = fetch_url(row.url, 30, "Stashy/1.0");
      if (!result) {
        db.mark_failed(row.id, "fetch failed");
        continue;
      }
      if (!result->error.empty()) {
        db.mark_failed(row.id, result->error);
        continue;
      }
      if (!db.insert_raw_page(row.id, row.url, result->html, result->status_code, result->content_type)) {
        db.mark_failed(row.id, "insert raw_page failed");
        continue;
      }
      db.mark_done(row.id);
    }
  }
}

void Engine::run() {
  std::cerr << "Engine: " << concurrency_ << " workers, batch=" << batch_size_
            << ", worker_id=" << worker_id_ << "\n";
  for (int i = 0; i < concurrency_; i++)
    threads_.emplace_back(&Engine::worker_thread, this, i);
  for (auto& t : threads_)
    t.join();
  threads_.clear();
}

}  // namespace stashy
