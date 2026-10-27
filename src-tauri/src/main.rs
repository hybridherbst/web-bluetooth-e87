#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod bluetooth;
mod jpeg;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

#[derive(Default)]
struct Transfer(AtomicBool);

#[tauri::command]
fn platform() -> &'static str {
    match std::env::consts::OS {
        "macos" => "darwin",
        "windows" => "win32",
        other => other,
    }
}

#[tauri::command]
fn set_transfer_active(active: bool, state: tauri::State<Transfer>) {
    state.0.store(active, Ordering::SeqCst);
}

#[tauri::command]
async fn save_payload(
    app: tauri::AppHandle,
    bytes: Vec<u8>,
    extension: String,
) -> Result<bool, String> {
    let valid = match extension.as_str() {
        "jpg" => bytes.starts_with(&[0xff, 0xd8, 0xff]),
        "avi" => bytes.starts_with(b"RIFF") && bytes.get(8..12) == Some(b"AVI "),
        _ => false,
    };
    if !valid || bytes.len() > 32 * 1024 * 1024 {
        return Err("Invalid or oversized badge file".into());
    }
    let path = app
        .dialog()
        .file()
        .set_title("Save badge content")
        .set_file_name(format!("e87.{}", extension))
        .add_filter("Badge content", &[&extension])
        .blocking_save_file();
    let Some(path) = path else { return Ok(false) };
    let path = path.into_path().map_err(|e| e.to_string())?;
    std::fs::write(path, bytes).map_err(|e| e.to_string())?;
    Ok(true)
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .manage(bluetooth::Bluetooth::default())
        .manage(Transfer::default())
        .setup(|app| {
            tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .on_navigation(|url| {
                    url.scheme() == "tauri"
                        || url.host_str() == Some("tauri.localhost")
                        || (cfg!(debug_assertions)
                            && url.host_str() == Some("localhost")
                            && url.port() == Some(1420))
                })
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            platform,
            save_payload,
            set_transfer_active,
            jpeg::encode_badge_jpeg,
            bluetooth::ble_scan,
            bluetooth::ble_select,
            bluetooth::ble_connect,
            bluetooth::ble_disconnect,
            bluetooth::ble_read,
            bluetooth::ble_write,
            bluetooth::ble_notify
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.state::<Transfer>().0.load(Ordering::SeqCst) {
                    api.prevent_close();
                    let _ = window.emit("transfer-close-blocked", ());
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Could not start E87 Studio");
    app.run(|app, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            if app.state::<Transfer>().0.load(Ordering::SeqCst) {
                api.prevent_exit();
                let _ = app.emit_to("main", "transfer-close-blocked", ());
            }
        }
    });
}
