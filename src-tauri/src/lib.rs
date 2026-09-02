mod commands;
mod engine;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_fs::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      commands::setup_engine(app.handle())?;
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![
      commands::engine_ping,
      commands::engine_health,
      commands::engine_call,
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}