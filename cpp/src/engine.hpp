#pragma once

#include "db.hpp"
#include "fetcher.hpp"
#include <string>
#include <atomic>
#include <cstdint>
#include <memory>
#include <thread>
#include <vector>

namespace stashy {

class Engine {
public:
  Engine(std::string conninfo, std::string worker_id, int concurrency, int batch_size);
  ~Engine();

  void run();
  void stop();

private:
  void worker_thread(int index);

  std::string conninfo_;
  std::string worker_id_;
  int concurrency_;
  int batch_size_;
  std::atomic<bool> running_{true};
  std::vector<std::thread> threads_;
};

}  // namespace stashy
