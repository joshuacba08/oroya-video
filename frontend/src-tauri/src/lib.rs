//! Desktop shell: starts the bundled Python backend, supervises it and stops it cleanly.
//!
//! - One app instance at a time (a second launch focuses the existing window).
//! - The backend gets a free port (8001 when available) and a random instance id; it is
//!   considered ready only when `/health` answers with that id, so an orphan or an older
//!   backend on the port is never mistaken for ours.
//! - Its stdout/stderr go to `storage/logs/backend-process.log` (startup crashes included).
//! - On Windows it runs inside a Job Object with kill-on-close: if the app dies, the backend
//!   and every ffmpeg/pip it started die with it.
//! - On exit the backend is asked to shut down (it pauses the running job and stops ffmpeg)
//!   and is only killed if it does not stop in time.
//! - If it exits unexpectedly it is restarted (twice at most); the UI follows the
//!   `backend-status` event.

use std::collections::hash_map::RandomState;
use std::fs::{self, OpenOptions};
use std::hash::{BuildHasher, Hasher};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, RunEvent};

const PREFERRED_PORT: u16 = 8001;
// Primer arranque lento (antivirus analizando python.exe): margen amplio.
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_RESTARTS: u32 = 2;
const PROCESS_LOG_MAX_BYTES: u64 = 5 * 1024 * 1024;
const BACKEND_SERVICE_NAME: &str = "Oroya Video Backend";

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendInfo {
    /// `external` (dev: backend started by hand), `starting`, `ready`, `exited`, `failed`.
    status: String,
    port: u16,
    error: Option<String>,
    logs_dir: Option<String>,
}

struct BackendState {
    info: Mutex<BackendInfo>,
    child: Mutex<Option<Child>>,
    instance_id: String,
    stopping: AtomicBool,
    #[cfg(windows)]
    job: Mutex<Option<win32job::Job>>,
}

impl BackendState {
    fn new(status: &str) -> Self {
        Self {
            info: Mutex::new(BackendInfo {
                status: status.into(),
                port: PREFERRED_PORT,
                error: None,
                logs_dir: None,
            }),
            child: Mutex::new(None),
            instance_id: random_token(),
            stopping: AtomicBool::new(false),
            #[cfg(windows)]
            job: Mutex::new(None),
        }
    }
}

fn random_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    (0..2)
        .map(|round| {
            let mut hasher = RandomState::new().build_hasher();
            hasher.write_u128(nanos);
            hasher.write_u32(std::process::id());
            hasher.write_u8(round);
            format!("{:016x}", hasher.finish())
        })
        .collect()
}

fn set_status(app: &AppHandle, status: &str, port: Option<u16>, error: Option<String>) {
    let state = app.state::<BackendState>();
    let snapshot = {
        let mut info = state.info.lock().unwrap();
        info.status = status.into();
        if let Some(port) = port {
            info.port = port;
        }
        info.error = error;
        info.clone()
    };
    let _ = app.emit("backend-status", snapshot);
}

#[tauri::command]
fn backend_info(state: tauri::State<'_, BackendState>) -> BackendInfo {
    state.info.lock().unwrap().clone()
}

fn port_is_free(port: u16) -> bool {
    let address = format!("127.0.0.1:{port}");
    let in_use = TcpStream::connect_timeout(
        &address.parse().expect("valid address"),
        Duration::from_millis(300),
    )
    .is_ok();
    !in_use && TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn choose_port() -> u16 {
    if port_is_free(PREFERRED_PORT) {
        return PREFERRED_PORT;
    }
    TcpListener::bind(("127.0.0.1", 0))
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .unwrap_or(PREFERRED_PORT)
}

/// Minimal HTTP/1.1 call to the local backend (no extra HTTP client dependency).
fn http_call(
    port: u16,
    method: &str,
    path: &str,
    headers: &[(&str, &str)],
    timeout: Duration,
) -> Option<(u16, String)> {
    let address = format!("127.0.0.1:{port}");
    let mut stream =
        TcpStream::connect_timeout(&address.parse().ok()?, Duration::from_millis(500)).ok()?;
    stream.set_read_timeout(Some(timeout)).ok()?;
    stream.set_write_timeout(Some(timeout)).ok()?;
    let extra: String = headers
        .iter()
        .map(|(name, value)| format!("{name}: {value}\r\n"))
        .collect();
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\
         Content-Length: 0\r\n{extra}\r\n"
    );
    stream.write_all(request.as_bytes()).ok()?;
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).ok()?;
    let response = String::from_utf8_lossy(&raw);
    let status = response.split_whitespace().nth(1)?.parse().ok()?;
    let body = response
        .split_once("\r\n\r\n")
        .map(|(_, body)| body.to_string())
        .unwrap_or_default();
    Some((status, body))
}

fn is_our_backend(port: u16, instance_id: &str) -> bool {
    let Some((200, body)) = http_call(port, "GET", "/api/v1/health", &[], Duration::from_secs(2))
    else {
        return false;
    };
    let Ok(payload) = serde_json::from_str::<serde_json::Value>(&body) else {
        return false;
    };
    payload["service"] == BACKEND_SERVICE_NAME && payload["instance_id"] == instance_id
}

fn open_process_log(logs_dir: &Path) -> Option<fs::File> {
    fs::create_dir_all(logs_dir).ok()?;
    let log_path = logs_dir.join("backend-process.log");
    if fs::metadata(&log_path).map(|meta| meta.len()).unwrap_or(0) > PROCESS_LOG_MAX_BYTES {
        let _ = fs::rename(&log_path, logs_dir.join("backend-process.log.1"));
    }
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)
        .ok()
}

struct BackendPaths {
    python: PathBuf,
    backend_dir: PathBuf,
    data_dir: PathBuf,
    logs_dir: PathBuf,
}

fn backend_paths(app: &AppHandle) -> Result<BackendPaths, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?;
    let backend_dir = resource_dir.join("backend");
    let python = backend_dir.join("python").join("python.exe");
    if !python.is_file() {
        return Err(format!("Bundled backend not found at {}", python.display()));
    }
    let data_dir = app
        .path()
        .app_local_data_dir()
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
    // Misma ruta que calcula el backend con OROYA_DATA_DIR (config.py).
    let logs_dir = data_dir.join("storage").join("logs");
    Ok(BackendPaths {
        python,
        backend_dir,
        data_dir,
        logs_dir,
    })
}

fn spawn_backend(app: &AppHandle, paths: &BackendPaths, port: u16) -> Result<Child, String> {
    let state = app.state::<BackendState>();
    let mut cmd = Command::new(&paths.python);
    cmd.args([
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &port.to_string(),
    ])
    .current_dir(&paths.backend_dir)
    .env("OROYA_DATA_DIR", &paths.data_dir)
    .env("OROYA_INSTANCE_ID", &state.instance_id)
    .env("PORT", port.to_string())
    .env("ENVIRONMENT", "production")
    .env("DEBUG", "false")
    .env("PYTHONNOUSERSITE", "1")
    .env("PYTHONUNBUFFERED", "1")
    // El backend también vigila este PID: si la app muere, se apaga solo.
    .env("OROYA_PARENT_PID", std::process::id().to_string())
    .stdin(Stdio::null());

    if let Some(log) = open_process_log(&paths.logs_dir) {
        if let Ok(stderr_log) = log.try_clone() {
            cmd.stdout(Stdio::from(log)).stderr(Stdio::from(stderr_log));
        }
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let child = cmd.spawn().map_err(|error| error.to_string())?;

    #[cfg(windows)]
    attach_to_kill_on_close_job(&state, &child);

    Ok(child)
}

#[cfg(windows)]
fn attach_to_kill_on_close_job(state: &BackendState, child: &Child) {
    use std::os::windows::io::AsRawHandle;

    let mut guard = state.job.lock().unwrap();
    if guard.is_none() {
        let job = win32job::Job::create().and_then(|job| {
            let mut limits = job.query_extended_limit_info()?;
            limits.limit_kill_on_job_close();
            job.set_extended_limit_info(&limits)?;
            Ok(job)
        });
        match job {
            Ok(job) => *guard = Some(job),
            Err(error) => {
                eprintln!("[oroya] could not create job object: {error}");
                return;
            }
        }
    }
    if let Some(job) = guard.as_ref() {
        if let Err(error) = job.assign_process(child.as_raw_handle() as isize) {
            eprintln!("[oroya] could not attach backend to job object: {error}");
        }
    }
}

/// `Some(exit description)` when the backend process has ended.
fn child_exit(state: &BackendState) -> Option<String> {
    let mut guard = state.child.lock().unwrap();
    let child = guard.as_mut()?;
    match child.try_wait() {
        Ok(Some(status)) => {
            guard.take();
            Some(format!("Backend exited ({status})"))
        }
        Ok(None) => None,
        Err(error) => {
            guard.take();
            Some(format!("Backend state unknown: {error}"))
        }
    }
}

fn kill_child(state: &BackendState) {
    if let Some(mut child) = state.child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn wait_until_ready(state: &BackendState, port: u16) -> Result<(), String> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    while Instant::now() < deadline {
        if state.stopping.load(Ordering::SeqCst) {
            return Err("App is closing".into());
        }
        if let Some(exit) = child_exit(state) {
            return Err(format!("{exit} during startup"));
        }
        if is_our_backend(port, &state.instance_id) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(400));
    }
    Err("Backend did not answer within the startup timeout".into())
}

fn supervise_backend(app: AppHandle) {
    let state = app.state::<BackendState>();
    let paths = match backend_paths(&app) {
        Ok(paths) => paths,
        Err(error) => {
            set_status(&app, "failed", None, Some(error));
            return;
        }
    };
    state.info.lock().unwrap().logs_dir = Some(paths.logs_dir.display().to_string());

    let mut restarts = 0;
    loop {
        if state.stopping.load(Ordering::SeqCst) {
            return;
        }
        let port = choose_port();
        set_status(&app, "starting", Some(port), None);

        let failure = match spawn_backend(&app, &paths, port) {
            Ok(child) => {
                *state.child.lock().unwrap() = Some(child);
                match wait_until_ready(&state, port) {
                    Ok(()) => {
                        set_status(&app, "ready", Some(port), None);
                        // Vigilancia: el backend no debería terminar mientras la app vive.
                        loop {
                            std::thread::sleep(Duration::from_secs(1));
                            if state.stopping.load(Ordering::SeqCst) {
                                return;
                            }
                            if let Some(exit) = child_exit(&state) {
                                break exit;
                            }
                        }
                    }
                    Err(error) => {
                        kill_child(&state);
                        error
                    }
                }
            }
            Err(error) => error,
        };

        if state.stopping.load(Ordering::SeqCst) {
            return;
        }
        restarts += 1;
        if restarts > MAX_RESTARTS {
            set_status(&app, "failed", None, Some(failure));
            return;
        }
        set_status(&app, "exited", None, Some(failure));
        std::thread::sleep(Duration::from_secs(2 * u64::from(restarts)));
    }
}

/// Graceful stop: ask the backend to shut down, wait, and kill only as a last resort.
fn stop_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    if state.stopping.swap(true, Ordering::SeqCst) {
        return;
    }
    if state.child.lock().unwrap().is_none() {
        return;
    }
    let port = state.info.lock().unwrap().port;
    let _ = http_call(
        port,
        "POST",
        "/api/v1/system/shutdown",
        &[("X-Oroya-Instance", state.instance_id.as_str())],
        Duration::from_secs(3),
    );
    let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
    while Instant::now() < deadline {
        if child_exit(&state).is_some() || state.child.lock().unwrap().is_none() {
            return;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    kill_child(&state);
}

/// "Reintentar" tras un fallo definitivo, o volver a arrancar el backend si una
/// actualización lo detuvo y después no pudo instalarse.
#[tauri::command]
fn restart_backend(app: AppHandle) {
    let state = app.state::<BackendState>();
    let stopped_for_update = state.stopping.load(Ordering::SeqCst);
    let failed = state.info.lock().unwrap().status == "failed";
    if !failed && !stopped_for_update {
        return;
    }
    if state.child.lock().unwrap().is_some() {
        return;
    }
    state.stopping.store(false, Ordering::SeqCst);
    let handle = app.clone();
    let _ = std::thread::Builder::new()
        .name("backend-supervisor".into())
        .spawn(move || supervise_backend(handle));
}

#[tauri::command]
fn stop_backend_for_update(app: AppHandle) {
    stop_backend(&app);
}

fn focus_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // En desarrollo el backend se arranca aparte (tauri dev / uvicorn en 8001).
    let bundled_backend = !cfg!(debug_assertions);

    tauri::Builder::default()
        // Debe ser el primer plugin: una segunda instancia solo enfoca la ventana existente.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            focus_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(BackendState::new(if bundled_backend {
            "starting"
        } else {
            "external"
        }))
        .invoke_handler(tauri::generate_handler![
            backend_info,
            restart_backend,
            stop_backend_for_update
        ])
        .setup(move |app| {
            if bundled_backend {
                let handle = app.handle().clone();
                std::thread::Builder::new()
                    .name("backend-supervisor".into())
                    .spawn(move || supervise_backend(handle))?;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                stop_backend(app_handle);
            }
            _ => {}
        });
}
