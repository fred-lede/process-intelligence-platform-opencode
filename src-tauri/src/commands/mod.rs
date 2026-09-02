//! Tauri IPC commands bridging the frontend to the analysis engine.

use std::time::Duration;

use crate::engine::EngineManager;
use serde_json::{json, Value};
use tauri::{Manager, State};

/// Tauri-managed application state.
pub struct AppState {
    pub engine: EngineManager,
}

/// Ping the analysis engine.
#[tauri::command]
pub fn engine_ping(state: State<'_, AppState>) -> Result<Value, String> {
    state
        .engine
        .call("engine/ping", json!({}), Duration::from_secs(10))
        .map_err(|e| e.to_string())
}

/// Read engine health status.
#[tauri::command]
pub fn engine_health(state: State<'_, AppState>) -> Result<Value, String> {
    state
        .engine
        .call("engine/health", json!({}), Duration::from_secs(10))
        .map_err(|e| e.to_string())
}

/// Generic RPC bridge: lets the frontend call any engine method.
#[tauri::command]
pub fn engine_call(
    method: String,
    params: Value,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    state
        .engine
        .call(&method, params, Duration::from_secs(120))
        .map_err(|e| e.to_string())
}

/// Initialize application state and start the engine on app setup.
pub fn setup_engine(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let engine = crate::engine::default_engine();
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