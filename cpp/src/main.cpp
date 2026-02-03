#include "engine.hpp"
#include <iostream>
#include <string>
#include <cstring>
#include <csignal>

static std::atomic<bool> g_running{true};

static void on_signal(int) { g_running = false; }

static void usage(const char* prog) {
  std::cerr << "Usage: " << prog << " [options]\n"
            << "  --db CONNINFO   PostgreSQL connection string (default: postgresql://crawler:crawler@localhost:5432/crawler)\n"
            << "  --workers N     Concurrency (default: 16)\n"
            << "  --batch N       URLs per claim batch (default: 20)\n"
            << "  --worker-id ID  Worker identifier (default: cpp-engine)\n";
}

int main(int argc, char* argv[]) {
  std::string conninfo = "postgresql://crawler:crawler@localhost:5432/crawler";
  std::string worker_id = "cpp-engine";
  int workers = 16;
  int batch = 20;

  for (int i = 1; i < argc; i++) {
    if (std::strcmp(argv[i], "--db") == 0 && i + 1 < argc) {
      conninfo = argv[++i];
    } else if (std::strcmp(argv[i], "--workers") == 0 && i + 1 < argc) {
      workers = std::atoi(argv[++i]);
    } else if (std::strcmp(argv[i], "--batch") == 0 && i + 1 < argc) {
      batch = std::atoi(argv[++i]);
    } else if (std::strcmp(argv[i], "--worker-id") == 0 && i + 1 < argc) {
      worker_id = argv[++i];
    } else if (std::strcmp(argv[i], "-h") == 0 || std::strcmp(argv[i], "--help") == 0) {
      usage(argv[0]);
      return 0;
    }
  }

  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);

  stashy::Engine engine(conninfo, worker_id, workers, batch);
  engine.run();
  return 0;
}
