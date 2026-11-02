pub mod supervisor;

use std::sync::{Arc, Mutex};
use tauri::{Manager, State};
use supervisor::{ServiceStatus, ServiceSupervisor, SharedSupervisor};

#[tauri::command]
fn get_service_status(supervisor: State<'_, SharedSupervisor>) -> Result<ServiceStatus, String> {
    let mut sup = supervisor.lock().map_err(|e| e.to_string())?;
    Ok(sup.status())
}

#[tauri::command]
fn get_session_token(supervisor: State<'_, SharedSupervisor>) -> Result<String, String> {
    let sup = supervisor.lock().map_err(|e| e.to_string())?;
    sup.session_token().map(|t| t.to_string())
}

fn resolve_base_dir(app_handle: &tauri::AppHandle) -> std::path::PathBuf {
    if let Ok(resource) = app_handle.path().resource_dir() {
        if supervisor::find_service_dir(&resource).is_some() {
            return resource;
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        if supervisor::find_service_dir(&cwd).is_some() {
            return cwd;
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            if supervisor::find_service_dir(parent).is_some() {
                return parent.to_path_buf();
            }
        }
    }
    std::env::current_dir().unwrap_or_default()
}

#[tauri::command]
fn start_vision_service(
    app_handle: tauri::AppHandle,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<ServiceStatus, String> {
    let mut sup = supervisor.lock().map_err(|e| e.to_string())?;
    let base_dir = resolve_base_dir(&app_handle);
    sup.start(base_dir)
}

#[tauri::command]
fn stop_vision_service(supervisor: State<'_, SharedSupervisor>) -> Result<ServiceStatus, String> {
    let mut sup = supervisor.lock().map_err(|e| e.to_string())?;
    sup.stop();
    Ok(sup.status())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let supervisor = Arc::new(Mutex::new(ServiceSupervisor::new("127.0.0.1", 8000)));
    let sup_clone = Arc::clone(&supervisor);

    tauri::Builder::default()
        .manage(supervisor)
        .setup(|app| {
            let base_dir = resolve_base_dir(app.handle());
            let sup = app.state::<SharedSupervisor>();
            let sup_inner = Arc::clone(&sup);

            // Initialize vision engine in background to ensure zero window load latency
            std::thread::spawn(move || {
                if let Ok(mut s) = sup_inner.lock() {
                    let _ = s.start(base_dir);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_service_status,
            get_session_token,
            start_vision_service,
            stop_vision_service
        ])
        .build(tauri::generate_context!())
        .expect("error while building Trinetra desktop application")
        .run(move |_app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit = event {
                if let Ok(mut sup) = sup_clone.lock() {
                    sup.stop();
                }
            }
        });
}
