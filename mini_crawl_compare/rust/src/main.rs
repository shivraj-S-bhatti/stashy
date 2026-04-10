use reqwest::Client;
use std::{
    env,
    fs::{self, File},
    io::Write,
    path::PathBuf,
    sync::Arc,
    time::Instant,
};
use tokio::{sync::Semaphore, task::JoinSet};

struct Row {
    id: usize,
    url: String,
    final_url: String,
    status: String,
    code: u16,
    ms: f64,
    bytes: usize,
    html_path: String,
    error: String,
}

fn looks_like_html(content_type: Option<&str>, body: &[u8]) -> bool {
    // Hint: keep the runtime simple. We only need a cheap HTML guess here.
    if let Some(ct) = content_type {
        if ct.contains("html") {
            return true;
        }
    }
    let head = String::from_utf8_lossy(&body[..body.len().min(256)]);
    head.contains("<html") || head.contains("<!DOCTYPE html")
}

fn p95(mut values: Vec<f64>) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.sort_by(|a, b| a.partial_cmp(b).unwrap());
    values[(0.95 * (values.len() as f64 - 1.0)) as usize]
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: cargo run --release -- URLS.txt RUN_DIR CONCURRENCY");
        std::process::exit(1);
    }

    let urls_path = PathBuf::from(&args[1]);
    let run_dir = PathBuf::from(&args[2]);
    let concurrency: usize = args[3].parse().unwrap_or(32).max(1);
    let urls: Vec<String> = fs::read_to_string(urls_path)?
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| line.to_string())
        .collect();

    fs::create_dir_all(run_dir.join("html"))?;
    let run_dir = fs::canonicalize(run_dir)?;
    let mut index = File::create(run_dir.join("index.tsv"))?;
    writeln!(
        index,
        "id\turl\tfinal_url\tstatus\tcode\tms\tbytes\thtml_path\terror"
    )?;

    // Hint: reqwest gives us a tiny high-level client, so most code can stay about policy.
    let client = Client::builder()
        .user_agent("mini-crawl-compare-rust/1.0")
        .redirect(reqwest::redirect::Policy::limited(10))
        .build()?;

    let limiter = Arc::new(Semaphore::new(concurrency));
    let wall_start = Instant::now();
    let mut set = JoinSet::new();

    for (i, url) in urls.iter().enumerate() {
        let permit = limiter.clone().acquire_owned().await?;
        let client = client.clone();
        let url = url.clone();
        let run_dir = run_dir.clone();

        set.spawn(async move {
            let _permit = permit;
            let started = Instant::now();

            let mut row = Row {
                id: i + 1,
                url: url.clone(),
                final_url: String::new(),
                status: "ok".into(),
                code: 0,
                ms: 0.0,
                bytes: 0,
                html_path: String::new(),
                error: String::new(),
            };

            match client.get(&url).send().await {
                Ok(resp) => {
                    row.code = resp.status().as_u16();
                    row.final_url = resp.url().to_string();
                    let content_type = resp
                        .headers()
                        .get(reqwest::header::CONTENT_TYPE)
                        .and_then(|v| v.to_str().ok())
                        .map(str::to_string);

                    match resp.bytes().await {
                        Ok(body) => {
                            row.bytes = body.len();
                            if row.code >= 400 {
                                row.status = "http_error".into();
                            }

                            if row.status == "ok" && looks_like_html(content_type.as_deref(), &body)
                            {
                                let html_path = run_dir.join("html").join(format!("{:06}.html", row.id));
                                tokio::fs::write(&html_path, &body).await?;
                                row.html_path = html_path.display().to_string();
                            }
                        }
                        Err(err) => {
                            row.status = "error".into();
                            row.error = err.to_string();
                        }
                    }
                }
                Err(err) => {
                    row.status = "error".into();
                    row.error = err.to_string();
                }
            }

            row.ms = started.elapsed().as_secs_f64() * 1000.0;
            Ok::<Row, Box<dyn std::error::Error + Send + Sync>>(row)
        });
    }

    let mut latencies = Vec::new();
    let mut ok = 0usize;
    let mut total_bytes = 0usize;

    // Hint: write results in one place so the TSV stays easy to inspect and debug.
    while let Some(done) = set.join_next().await {
        let row = done??;
        latencies.push(row.ms);
        total_bytes += row.bytes;
        if row.status == "ok" {
            ok += 1;
        }

        writeln!(
            index,
            "{}\t{}\t{}\t{}\t{}\t{:.2}\t{}\t{}\t{}",
            row.id,
            row.url,
            row.final_url,
            row.status,
            row.code,
            row.ms,
            row.bytes,
            row.html_path,
            row.error.replace('\t', " ")
        )?;
    }

    let wall_ms = wall_start.elapsed().as_secs_f64() * 1000.0;
    let avg_ms = if latencies.is_empty() {
        0.0
    } else {
        latencies.iter().sum::<f64>() / latencies.len() as f64
    };
    let pages_per_sec = if wall_ms == 0.0 {
        0.0
    } else {
        1000.0 * urls.len() as f64 / wall_ms
    };

    println!(
        "rust fetched={}/{} avg_ms={:.1} p95_ms={:.1} pages_per_sec={:.2} total_bytes={}",
        ok,
        urls.len(),
        avg_ms,
        p95(latencies),
        pages_per_sec,
        total_bytes
    );

    Ok(())
}
