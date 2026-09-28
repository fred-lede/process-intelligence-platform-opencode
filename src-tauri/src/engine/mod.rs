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
use std::fs::{create_dir_all, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use serde_json::{json, Value};

fn append_runtime_log(message: &str) {
    let Some(home) = std::env::var_os("HOME") else { return };
    let path = PathBuf::from(home).join("Library/Logs/Process Intelligence Platform/engine.log");
    if let Some(parent) = path.parent() { let _ = create_dir_all(parent); }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{message}");
    }
}

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

/// Everything needed to spawn the engine child process.
///
/// The engine can be launched in two shapes: a frozen standalone executable
/// (how shipped builds work) or a Python interpreter running the package
/// module (how development works). Both speak the same JSON-lines protocol.
#[derive(Debug, Clone)]
pub struct EngineLaunch {
    /// Executable to spawn.
    pub program: PathBuf,
    /// Arguments passed to the executable.
    pub args: Vec<String>,
    /// Working directory for the child, when one is required.
    pub working_dir: Option<PathBuf>,
    /// Which candidate matched, for logs and error messages.
    pub source: &'static str,
}

/// Module invoked when the engine is launched through a Python interpreter.
const ENGINE_MODULE: &str = "process_intelligence_engine.main";

/// Name of the frozen engine executable produced by `scripts/build-engine.mjs`.
fn frozen_engine_name() -> &'static str {
    if cfg!(windows) {
        "process-intelligence-engine.exe"
    } else {
        "process-intelligence-engine"
    }
}

/// Interpreter path inside a virtualenv, which differs by platform.
fn venv_python(venv_root: &std::path::Path) -> PathBuf {
    if cfg!(windows) {
        venv_root.join("Scripts").join("python.exe")
    } else {
        venv_root.join("bin").join("python")
    }
}

/// Build the launch spec for a Python interpreter running the engine module.
fn python_launch(python: PathBuf, working_dir: Option<PathBuf>, source: &'static str) -> EngineLaunch {
    EngineLaunch {
        program: python,
        args: vec!["-m".to_string(), ENGINE_MODULE.to_string()],
        working_dir,
        source,
    }
}

/// Decide how to start the engine.
///
/// Resolution order, first match wins:
///
/// 1. `PROCESS_INTELLIGENCE_ENGINE` — explicit developer/support override. If
///    the value names a Python interpreter the package module is run, so
///    pointing it at a hand-made venv works; otherwise it is executed directly.
/// 2. The frozen engine shipped inside the app bundle
///    (`$RESOURCE/engine/process-intelligence-engine[.exe]`).
/// 3. A virtualenv shipped inside the app bundle (`$RESOURCE/engine/venv/…`).
/// 4. The development checkout's `engine/.venv/…`.
///
/// When nothing matches, every path that was tried is reported so the failure
/// names the missing artifact instead of surfacing as a generic start error.
pub fn resolve_launch(resources_dir: Option<&std::path::Path>) -> std::result::Result<EngineLaunch, String> {
    let mut tried: Vec<String> = Vec::new();

    if let Some(raw) = std::env::var_os("PROCESS_INTELLIGENCE_ENGINE") {
        let override_path = PathBuf::from(&raw);
        let looks_like_python = override_path
            .file_name()
            .and_then(|n| n.to_str())
            .map(|n| n.starts_with("python"))
            .unwrap_or(false);
        let display = override_path.display().to_string();
        tried.push(format!("[PROCESS_INTELLIGENCE_ENGINE] {display}"));
        if looks_like_python {
            return Ok(python_launch(override_path, None, "PROCESS_INTELLIGENCE_ENGINE"));
        }
        return Ok(EngineLaunch {
            program: override_path,
            args: Vec::new(),
            working_dir: None,
            source: "PROCESS_INTELLIGENCE_ENGINE",
        });
    }

    if let Some(resources) = resources_dir {
        let engine_dir = resources.join("engine");

        let frozen = engine_dir.join(frozen_engine_name());
        if frozen.is_file() {
            return Ok(EngineLaunch {
                program: frozen,
                args: Vec::new(),
                working_dir: Some(engine_dir),
                source: "bundled frozen engine",
            });
        }
        tried.push(frozen.display().to_string());

        let bundled_venv_python = venv_python(&engine_dir.join("venv"));
        if bundled_venv_python.is_file() {
            return Ok(python_launch(
                bundled_venv_python,
                Some(engine_dir.clone()),
                "bundled virtualenv",
            ));
        }
        tried.push(bundled_venv_python.display().to_string());
    } else {
        tried.push("(no resource directory available)".to_string());
    }

    // Development checkout: `engine/.venv` next to `src-tauri/`.
    if let Some(repo_root) = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent() {
        let engine_root = repo_root.join("engine");
        let dev_python = venv_python(&engine_root.join(".venv"));
        if dev_python.is_file() {
            return Ok(python_launch(dev_python, Some(engine_root), "development virtualenv"));
        }
        tried.push(dev_python.display().to_string());
    }

    Err(format!(
        "no analysis engine found. Install the packaged app, or run \
         `cd engine && uv venv --python 3.12 && uv sync --extra dev`, or set \
         PROCESS_INTELLIGENCE_ENGINE to the engine executable. Paths tried:\n  - {}",
        tried.join("\n  - ")
    ))
}

/// Manages the Python engine subprocess and its request/response loop.
pub struct EngineManager {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    pending: Pending,
    next_id: Mutex<u64>,
    launch: EngineLaunch,
}

impl EngineManager {
    /// Create a new manager from a resolved launch spec.
    pub fn new(launch: EngineLaunch) -> Self {
        Self {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
            pending: Arc::new(Mutex::new(HashMap::new())),
            next_id: Mutex::new(0),
            launch,
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

        log::info!(
            "starting engine from {} ({}), program={} args={:?}",
            self.launch.source,
            self.launch.program.display(),
            self.launch.program.display(),
            self.launch.args
        );

        let mut cmd = Command::new(&self.launch.program);
        if let Some(dir) = self.launch.working_dir.as_ref() {
            cmd.current_dir(dir);
        }
        cmd.args(&self.launch.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(target_os = "macos")]
        configure_macos_weasyprint_libraries(&mut cmd);

        let mut child = cmd.spawn().map_err(|e| {
            EngineError::Start(format!(
                "could not launch {} engine at {}: {e}",
                self.launch.source,
                self.launch.program.display()
            ))
        })?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| EngineError::Start("could not capture stdin".into()))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| EngineError::Start("could not capture stdout".into()))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| EngineError::Start("could not capture stderr".into()))?;

        // Reader thread for stderr: drain + log so a chatty engine can never
        // block itself writing into a full pipe.
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                match line {
                    Ok(l) => { append_runtime_log(&format!("[engine:stderr] {l}")); log::info!("[engine:stderr] {l}"); },
                    Err(_) => break,
                }
            }
            log::info!("engine stderr closed");
        });

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

#[cfg(target_os = "macos")]
fn configure_macos_weasyprint_libraries(cmd: &mut Command) {
    let homebrew_lib = if std::path::Path::new("/opt/homebrew/lib").is_dir() {
        "/opt/homebrew/lib"
    } else if std::path::Path::new("/usr/local/lib").is_dir() {
        "/usr/local/lib"
    } else {
        return;
    };

    let inherited = std::env::var("DYLD_FALLBACK_LIBRARY_PATH").unwrap_or_default();
    let value = if inherited.is_empty() {
        homebrew_lib.to_string()
    } else {
        format!("{homebrew_lib}:{inherited}")
    };
    cmd.env("DYLD_FALLBACK_LIBRARY_PATH", value);
}

impl Drop for EngineManager {
    fn drop(&mut self) {
        self.kill_child();
    }
}

/// Build an EngineManager for the given resource directory.
///
/// `resources_dir` is `app.path().resource_dir()` in the running app; pass
/// `None` (tests, CLI tools) to resolve against the development checkout only.
pub fn default_engine(resources_dir: Option<PathBuf>) -> Result<EngineManager> {
    let launch = resolve_launch(resources_dir.as_deref()).map_err(EngineError::Start)?;
    append_runtime_log(&format!(
        "engine launch: source={} program={} args={:?}",
        launch.source,
        launch.program.display(),
        launch.args
    ));
    Ok(EngineManager::new(launch))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pings_live_engine() {
        let manager = default_engine(None).expect("engine launch should resolve");
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
        // The time-series sample, not `test_dataset.csv`: that file was
        // regenerated to the multi-level template (input_*/output_*/result) and
        // no longer carries `time` or `temperature`, which is what this test
        // used to ask for. It went unnoticed because there was no CI running
        // these tests.
        let csv = std::path::Path::new(manifest)
            .parent()
            .unwrap()
            .join("data")
            .join("test_dataset_timeseries.csv");
        let manager = default_engine(None).expect("engine launch should resolve");
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
                    "time_column": "datetime",
                    "value_columns": ["input_temperature"],
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

    #[test]
    fn frozen_engine_name_matches_build_script() {
        // scripts/build-engine.mjs stages the PyInstaller bundle under exactly
        // this name; renaming one side silently breaks shipping builds.
        assert_eq!(
            frozen_engine_name(),
            if cfg!(windows) {
                "process-intelligence-engine.exe"
            } else {
                "process-intelligence-engine"
            }
        );
    }

    #[test]
    fn venv_python_uses_platform_layout() {
        let root = std::path::Path::new("/tmp/does-not-matter");
        let python = venv_python(root);
        if cfg!(windows) {
            assert_eq!(python, root.join("Scripts").join("python.exe"));
        } else {
            assert_eq!(python, root.join("bin").join("python"));
        }
    }

    #[test]
    fn unresolved_engine_reports_every_path_tried() {
        let missing = std::path::PathBuf::from("/nonexistent-resource-dir-for-test");
        match resolve_launch(Some(&missing)) {
            // A development venv may legitimately satisfy this checkout; it
            // must not, however, have come from the bogus resource directory.
            Ok(launch) => assert!(!launch.program.starts_with(&missing)),
            Err(message) => {
                assert!(message.contains("no analysis engine found"), "{message}");
                assert!(message.contains("nonexistent-resource-dir-for-test"), "{message}");
            }
        }
    }
}
