use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent};

struct BackendProcess(Mutex<Option<Child>>);

const BACKEND_PORT: u16 = 8001;
const BACKEND_STARTUP_TIMEOUT: Duration = Duration::from_secs(25);

fn spawn_backend(app: &tauri::App) -> Result<Option<Child>, Box<dyn std::error::Error>> {
    let resource_dir = app.path().resource_dir()?;
    let backend_dir = resource_dir.join("backend");
    let python = backend_dir.join("python").join("python.exe");

    if !python.is_file() {
        // Build de desarrollo o backend no empaquetado: el usuario lo arranca aparte.
        eprintln!("[oroya] bundled backend not found at {python:?}; skipping spawn");
        return Ok(None);
    }

    let data_dir = app.path().app_local_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;

    let mut cmd = Command::new(&python);
    cmd.args([
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &BACKEND_PORT.to_string(),
    ])
    .current_dir(&backend_dir)
    .env("OROYA_DATA_DIR", &data_dir)
    .env("PORT", BACKEND_PORT.to_string())
    .env("ENVIRONMENT", "production")
    .env("DEBUG", "false")
    .env("PYTHONNOUSERSITE", "1")
    // El backend vigila este PID y se apaga si la app muere sin pasar por RunEvent::Exit
    // (crash o cierre forzado), para no dejar un backend huérfano en el puerto.
    .env("OROYA_PARENT_PID", std::process::id().to_string());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let child = cmd.spawn()?;
    wait_for_backend(BACKEND_PORT);
    Ok(Some(child))
}

fn wait_for_backend(port: u16) {
    let deadline = Instant::now() + BACKEND_STARTUP_TIMEOUT;
    let address = format!("127.0.0.1:{port}");
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(
            &address.parse().expect("valid backend address"),
            Duration::from_millis(500),
        )
        .is_ok()
        {
            return;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    eprintln!("[oroya] backend did not become reachable within the startup timeout");
}

fn kill_backend(app_handle: &tauri::AppHandle) {
    if let Some(state) = app_handle.try_state::<BackendProcess>() {
        if let Ok(mut guard) = state.0.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            if !cfg!(debug_assertions) {
                match spawn_backend(app) {
                    Ok(child) => {
                        *app.state::<BackendProcess>().0.lock().unwrap() = child;
                    }
                    Err(error) => {
                        eprintln!("[oroya] failed to spawn bundled backend: {error}");
                    }
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                kill_backend(app_handle);
            }
            _ => {}
        });
}
