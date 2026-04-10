#include <curl/curl.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <numeric>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

struct Job {
  std::size_t id{};
  std::string url;
  std::string body;
  Clock::time_point start;
};

// Hint: keep this callback tiny. libcurl will call it many times per response.
static size_t write_cb(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* body = static_cast<std::string*>(userdata);
  body->append(ptr, size * nmemb);
  return size * nmemb;
}

static std::vector<std::string> load_urls(const fs::path& path) {
  std::ifstream in(path);
  std::vector<std::string> urls;
  for (std::string line; std::getline(in, line);) {
    if (!line.empty()) urls.push_back(line);
  }
  return urls;
}

static bool looks_like_html(const char* content_type, const std::string& body) {
  if (content_type && std::string(content_type).find("html") != std::string::npos) return true;
  return body.find("<html") != std::string::npos || body.find("<!DOCTYPE html") != std::string::npos;
}

static double p95(std::vector<double> values) {
  if (values.empty()) return 0.0;
  std::sort(values.begin(), values.end());
  return values[static_cast<std::size_t>(0.95 * (values.size() - 1))];
}

int main(int argc, char** argv) {
  if (argc < 4) {
    std::cerr << "usage: ./crawl_cpp URLS.txt RUN_DIR CONCURRENCY\n";
    return 1;
  }

  const fs::path urls_path = argv[1];
  const fs::path run_dir = fs::absolute(argv[2]);
  const int concurrency = std::max(1, std::stoi(argv[3]));
  const auto urls = load_urls(urls_path);

  fs::create_directories(run_dir / "html");
  std::ofstream index(run_dir / "index.tsv");
  index << "id\turl\tfinal_url\tstatus\tcode\tms\tbytes\thtml_path\terror\n";

  curl_global_init(CURL_GLOBAL_DEFAULT);
  CURLM* multi = curl_multi_init();

  std::unordered_map<CURL*, std::unique_ptr<Job>> jobs;
  std::vector<double> latencies_ms;
  std::size_t next = 0;
  std::size_t ok = 0;
  std::size_t total_bytes = 0;
  const auto wall_start = Clock::now();

  auto launch = [&](std::size_t id, const std::string& url) {
    auto job = std::make_unique<Job>();
    job->id = id;
    job->url = url;
    job->start = Clock::now();

    CURL* easy = curl_easy_init();
    curl_easy_setopt(easy, CURLOPT_URL, job->url.c_str());
    curl_easy_setopt(easy, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(easy, CURLOPT_ACCEPT_ENCODING, "");
    curl_easy_setopt(easy, CURLOPT_USERAGENT, "mini-crawl-compare-cpp/1.0");
    curl_easy_setopt(easy, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(easy, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(easy, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_2TLS);
    curl_easy_setopt(easy, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(easy, CURLOPT_WRITEDATA, &job->body);
    curl_easy_setopt(easy, CURLOPT_PRIVATE, job.get());

    jobs[easy] = std::move(job);
    curl_multi_add_handle(multi, easy);
  };

  // Hint: this loop is the whole crawler. Multi-handle + a small launch policy.
  while (next < urls.size() || !jobs.empty()) {
    while (next < urls.size() && static_cast<int>(jobs.size()) < concurrency) {
      launch(next + 1, urls[next]);
      ++next;
    }

    int still_running = 0;
    curl_multi_perform(multi, &still_running);
    curl_multi_poll(multi, nullptr, 0, 1000, nullptr);

    int msg_count = 0;
    while (CURLMsg* msg = curl_multi_info_read(multi, &msg_count)) {
      if (msg->msg != CURLMSG_DONE) continue;

      CURL* easy = msg->easy_handle;
      auto it = jobs.find(easy);
      if (it == jobs.end()) continue;
      Job& job = *it->second;

      long code = 0;
      char* effective = nullptr;
      char* content_type = nullptr;
      curl_easy_getinfo(easy, CURLINFO_RESPONSE_CODE, &code);
      curl_easy_getinfo(easy, CURLINFO_EFFECTIVE_URL, &effective);
      curl_easy_getinfo(easy, CURLINFO_CONTENT_TYPE, &content_type);

      const double ms =
          std::chrono::duration<double, std::milli>(Clock::now() - job.start).count();
      latencies_ms.push_back(ms);
      total_bytes += job.body.size();

      std::string status = "ok";
      std::string error;
      if (msg->data.result != CURLE_OK) {
        status = "error";
        error = curl_easy_strerror(msg->data.result);
      } else if (code >= 400) {
        status = "http_error";
      }

      std::string html_path;
      if (status == "ok" && looks_like_html(content_type, job.body)) {
        char name[32];
        std::snprintf(name, sizeof(name), "%06zu.html", job.id);
        html_path = (run_dir / "html" / name).string();
        std::ofstream(html_path) << job.body;
      }

      if (status == "ok") ++ok;

      index << job.id << '\t' << job.url << '\t' << (effective ? effective : "") << '\t'
            << status << '\t' << code << '\t' << std::fixed << std::setprecision(2) << ms
            << '\t' << job.body.size() << '\t' << html_path << '\t' << error << '\n';

      curl_multi_remove_handle(multi, easy);
      curl_easy_cleanup(easy);
      jobs.erase(it);
    }
  }

  const double wall_ms =
      std::chrono::duration<double, std::milli>(Clock::now() - wall_start).count();
  const double pages_per_sec = urls.empty() ? 0.0 : (1000.0 * urls.size()) / wall_ms;
  const double avg_ms =
      latencies_ms.empty() ? 0.0 : std::accumulate(latencies_ms.begin(), latencies_ms.end(), 0.0) / latencies_ms.size();

  std::cout << "cpp fetched=" << ok << "/" << urls.size()
            << " avg_ms=" << std::fixed << std::setprecision(1) << avg_ms
            << " p95_ms=" << p95(latencies_ms)
            << " pages_per_sec=" << pages_per_sec
            << " total_bytes=" << total_bytes << "\n";

  curl_multi_cleanup(multi);
  curl_global_cleanup();
  return 0;
}
