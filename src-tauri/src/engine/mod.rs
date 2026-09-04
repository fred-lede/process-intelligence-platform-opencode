//! Python analysis engine management.
//!
//! The engine runs as a long-lived child process. This module owns the
//! subprocess lifecycle and implements a synchronous JSON-RPC client over
//! the child's stdin/stdout.
//!
//! Protocol (JSON lines):
//!   request:  {"id": "...", "method": "...", "params": {...}}
//!   response: {"id": "...", "result": {...}}
//!           or {"id": "...", "error": {"message": "...", "traceback": "..."}}

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use serde_json::{json, Value};

/// Errors emitted by the engine client.
#[derive(Debug)]
pub enum EngineError {
    Start(String),
    NotRunning,
    Write(String),
    Read(String),
    Parse(String),
    Timeout(Duration),
    Remote { message: String },
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EngineError::Start(msg) => write!(f, "failed to start engine: {msg}"),
            EngineError::NotRunning => write!(f, "engine is not running"),
            EngineError::Write(msg) => write!(f, "failed to write to engine: {msg}"),
            EngineError::Read(msg) => write!(f, "failed to read from engine: {msg}"),
            EngineError::Parse(msg) => write!(f, "failed to parse engine response: {msg}"),
            EngineError::Timeout(t) => write!(f, "engine call timed out after {t:?}"),
            EngineError::Remote { message } => write!(f, "engine error: {message}"),
        }
    }
}

impl std::error::Error for EngineError {}

/// Result type for engine operations.
pub type Result<T> = std::result::Result<T, EngineError>;

/// Pending request registry shared between the manager and the reader thread.
type Pending = Arc<Mutex<HashMap<String, mpsc::Sender<Value>>>>;

/// Manages the Python engine subprocess and its request/response loop.
pub struct EngineManager {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    pending: Pending,
    next_id: Mutex<u64>,
    python_path: String,
    engine_module: String,
}

impl EngineManager {
    /// Create a new manager. `python_path` is checked at start time.
    pub fn new(python_path: impl Into<String>, engine_module: impl Into<String>) -> Self {
        Self {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
            pending: Arc::new(Mutex::new(HashMap::new())),
            next_id: Mutex::new(0),
            python_path: python_path.into(),
            engine_module: engine_module.into(),
        }
    }

    /// Terminate any running child.
    fn kill_child(&self) {
        if let Ok(mut pending) = self.pending.lock() {
            pending.clear();
        }
        if let Ok(mut child) = self.child.lock() {
            if let Some(c) = child.as_mut() {
                let _ = c.kill();
                let _ = c.wait();
            }
            *child = None;
        }
        if let Ok(mut stdin) = self.stdin.lock() {
            *stdin = None;
        }
    }

    /// Start the engine subprocess.
    pub fn start(&self) -> Result<()> {
        self.kill_child();

        let mut cmd = Command::new(&self.python_path);
        cmd.arg("-m")
            .arg(&self.engine_module)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let mut child = cmd
            .spawn()
            .map_err(|e| EngineError::Start(e.to_string()))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| EngineError::Start("could not capture stdin".into()))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| EngineError::Start("could not capture stdout".into()))?;

        // Reader thread: dispatch responses to pending senders by id.
        let pending = Arc::clone(&self.pending);
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut line = String::new();
                match reader.read_line(&mut line) {
                    Ok(0) | Err(_) => break, // EOF / error
                    Ok(_) => {}
                }
                if line.trim().is_empty() {
                    continue;
                }
                let value: Value = match serde_json::from_str(&line) {
                    Ok(v) => v,
                    Err(_) => continue,
                };
                let id = value
                    .get("id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                if let Ok(mut pending) = pending.lock() {
                    if let Some(tx) = pending.remove(&id) {
                        let _ = tx.send(value);
                    }
                }
            }
        });

        *self
            .stdin
            .lock()
            .map_err(|_| EngineError::Start("lock poisoned".into()))? = Some(stdin);
        *self
            .child
            .lock()
            .map_err(|_| EngineError::Start("lock poisoned".into()))? = Some(child);

        // Verify the engine is responsive.
        let resp = self.call("engine/ping", json!({}), Duration::from_secs(10))?;
        if resp.get("pong") != Some(&Value::Bool(true)) {
            self.kill_child();
            return Err(EngineError::Start("engine did not respond to ping".into()));
        }
        Ok(())
    }

    /// Issue an RPC call and wait for the response.
    pub fn call(&self, method: &str, params: Value, timeout: Duration) -> Result<Value> {
        let id = {
            let mut next = self.next_id.lock().map_err(|_| EngineError::NotRunning)?;
            *next += 1;
            next.to_string()
        };

        let (tx, rx) = mpsc::channel();

        self.pending
            .lock()
            .map_err(|_| EngineError::NotRunning)?
            .insert(id.clone(), tx);

        let request = serde_json::json!({
            "id": id,
            "method": method,
            "params": params,
        });

        {
            let mut stdin_guard = self.stdin.lock().map_err(|_| EngineError::NotRunning)?;
            let stdin = stdin_guard.as_mut().ok_or(EngineError::NotRunning)?;
            let line = serde_json::to_string(&request)
                .map_err(|e| EngineError::Parse(e.to_string()))?;
            writeln!(stdin, "{line}")
                .and_then(|_| stdin.flush())
                .map_err(|e| EngineError::Write(e.to_string()))?;
        }

        match rx.recv_timeout(timeout) {
            Ok(value) => {
                if value.get("error").is_some() {
                    let msg = value
                        .pointer("/error/message")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown error");
                    return Err(EngineError::Remote { message: msg.into() });
                }
                Ok(value.get("result").cloned().unwrap_or(Value::Null))
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                self.pending.lock().ok().and_then(|mut p| p.remove(&id));
                Err(EngineError::Timeout(timeout))
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                Err(EngineError::Read("engine process exited".into()))
            }
        }
    }

    /// Stop the engine gracefully.
    pub fn stop(&self) {
        self.kill_child();
    }
}

impl Drop for EngineManager {
    fn drop(&mut self) {
        self.kill_child();
    }
}

/// Build a fresh EngineManager pointing at the bundled engine module.
pub fn default_engine() -> EngineManager {
    // Dev: the engine lives in `engine/` relative to the repo root, with a
    // venv at `.venv/bin/python`. In a bundled build the path is resolved
    // at runtime from the app resource dir instead.
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let python = std::path::Path::new(manifest_dir)
        .parent()
        .map(|root| root.join("engine").join(".venv").join("bin").join("python"))
        .unwrap_or_else(|| std::path::PathBuf::from("./engine/.venv/bin/python"));

    let python = python.to_string_lossy().to_string();
    log::info!("engine python path: {python}");
    EngineManager::new(python, "process_intelligence_engine.main")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pings_live_engine() {
        let manager = default_engine();
        manager.start().expect("engine should start");
        let resp = manager
            .call("engine/ping", json!({}), Duration::from_secs(10))
            .expect("ping should succeed");
        assert_eq!(resp.get("pong"), Some(&Value::Bool(true)));
        manager.stop();
    }

    #[test]
    fn time_series_returns_fast_live_engine() {
        let manifest = env!("CARGO_MANIFEST_DIR");
        let csv = std::path::Path::new(manifest)
            .parent()
            .unwrap()
            .join("data")
            .join("test_dataset.csv");
        let manager = default_engine();
        manager.start().expect("engine should start");

        let imported = manager
            .call(
                "data/import",
                json!({ "file_path": csv.to_string_lossy() }),
                Duration::from_secs(10),
            )
            .expect("import should succeed");
        let dataset_id = imported["dataset_id"]
            .as_str()
            .expect("dataset_id present")
            .to_string();

        let start = std::time::Instant::now();
        let resp = manager
            .call(
                "features/time_series",
                json!({
                    "dataset_id": dataset_id,
                    "time_column": "time",
                    "value_columns": ["temperature"],
                    "window_sizes": [3, 5, 10],
                }),
                Duration::from_secs(10),
            )
            .expect("time_series should succeed");
        let elapsed = start.elapsed();
        assert!(resp.get("n_features").is_some(), "n_features present");
        assert!(
            elapsed.as_secs() < 10,
            "time_series should return fast, took {:?}",
            elapsed
        );
        eprintln!("time_series took {:?}", elapsed);
        manager.stop();
    }
}