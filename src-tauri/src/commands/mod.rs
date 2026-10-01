//! Tauri IPC commands bridging the frontend to the analysis engine.

use std::time::Duration;

use crate::engine::EngineManager;
use serde_json::{json, Value};
use tauri::{Manager, State};

/// Tauri-managed application state.
pub struct AppState {
    pub engine: std::sync::Arc<EngineManager>,
}

/// Ping the analysis engine.
#[tauri::command]
pub async fn engine_ping(state: State<'_, AppState>) -> Result<Value, String> {
    let engine = state.engine.clone();
    // Run on a blocking task so a slow engine does not freeze the UI main
    // thread (sync tauri commands otherwise execute on the main thread).
    tauri::async_runtime::spawn_blocking(move || {
        engine
            .call("engine/ping", json!({}), Duration::from_secs(10))
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Read engine health status.
#[tauri::command]
pub async fn engine_health(state: State<'_, AppState>) -> Result<Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        engine
            .call("engine/health", json!({}), Duration::from_secs(10))
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Generic RPC bridge: lets the frontend call any engine method.
#[tauri::command]
pub async fn engine_call(
    method: String,
    params: Value,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        engine
            .call(&method, params, Duration::from_secs(210))
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Initialize application state and start the engine on app setup.
pub fn setup_engine(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    // In a packaged app the frozen engine is shipped under the resource
    // directory; in development the resolver falls back to `engine/.venv`.
    let resources_dir = app.path().resource_dir().ok();
    let engine = std::sync::Arc::new(crate::engine::default_engine(resources_dir)?);
    let state = AppState { engine };
    app.manage(state);

    // Start the engine in the background; log but don't fail startup.
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let state = app_handle.state::<AppState>();
        if let Err(e) = state.engine.start() {
            log::error!("engine start failed: {e}");
        }
    });

    Ok(())
}

/// Write a generated report into the app cache and open it with the OS default viewer.
///
/// The write happens here rather than through the fs plugin on purpose: that capability is
/// scoped to paths the user picks in a file dialog, and a cache path is not one of them.
/// Doing it in Rust also avoids a plugin and a permission for what is a single OS call, and
/// keeps the webview layer untouched.
#[tauri::command]
pub async fn open_report(
    app: tauri::AppHandle,
    file_name: String,
    content_base64: String,
) -> Result<String, String> {
    use base64::Engine as _;

    // Base name only: a crafted name must not escape the cache directory via "../".
    let base = file_name.rsplit(['/', '\\']).next().unwrap_or("").trim();
    if base.is_empty() || base == "." || base == ".." {
        return Err(format!("invalid report file name: {file_name:?}"));
    }

    let dir = app
        .path()
        .app_cache_dir()
        .map_err(|e| format!("no cache directory: {e}"))?
        .join("reports");
    std::fs::create_dir_all(&dir).map_err(|e| format!("cannot create {}: {e}", dir.display()))?;

    let bytes = base64::engine::general_purpose::STANDARD
        .decode(content_base64.as_bytes())
        .map_err(|e| format!("invalid report payload: {e}"))?;

    let path = dir.join(base);
    std::fs::write(&path, &bytes).map_err(|e| format!("cannot write {}: {e}", path.display()))?;

    // A report is small enough that the write above is not worth a thread hop, but the
    // viewer is handed off and not waited on -- a slow or missing viewer must not hold the
    // command open, and its failure is reported rather than swallowed.
    let opener = if cfg!(target_os = "macos") {
        "open"
    } else if cfg!(target_os = "windows") {
        "explorer"
    } else {
        "xdg-open"
    };
    std::process::Command::new(opener)
        .arg(&path)
        .spawn()
        .map_err(|e| format!("cannot open {} with {opener}: {e}", path.display()))?;

    log::info!("opened report {}", path.display());
    Ok(path.to_string_lossy().to_string())
}
