use btleplug::{
    api::{
        Central, CentralEvent, CharPropFlags, Characteristic, Manager as _, Peripheral as _,
        ScanFilter, WriteType,
    },
    platform::{Adapter, Manager, Peripheral},
};
use futures::StreamExt;
use serde::Serialize;
use std::{collections::HashMap, sync::Arc, time::Duration};
use tauri::async_runtime::JoinHandle;
use tauri::{Emitter, Manager as _, State};
use tokio::{sync::Mutex, time::timeout};
use uuid::Uuid;

#[derive(Default)]
pub struct Bluetooth(Mutex<Inner>);
#[derive(Default)]
struct Inner {
    adapter: Option<Adapter>,
    scan: Option<Scan>,
    selected: Option<(u32, Peripheral)>,
    connection: Option<Arc<Connection>>,
}
struct Scan {
    id: u32,
    devices: HashMap<String, (Peripheral, Device)>,
    task: Option<JoinHandle<()>>,
}
struct Connection {
    id: u32,
    peripheral: Peripheral,
    characteristics: Vec<Characteristic>,
    writes: Mutex<()>,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Device {
    device_id: String,
    device_name: String,
    advertised_mac: Option<String>,
    rssi: Option<i16>,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ScanEvent {
    request_id: u32,
    devices: Vec<Device>,
    error: Option<String>,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct Notification {
    session_id: u32,
    uuid: String,
    value: Vec<u8>,
}
#[derive(Serialize)]
pub struct Service {
    uuid: String,
    characteristics: Vec<CharInfo>,
}
#[derive(Serialize)]
pub struct CharInfo {
    uuid: String,
    properties: Properties,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Properties {
    read: bool,
    write: bool,
    write_without_response: bool,
    notify: bool,
    indicate: bool,
}

fn error(e: impl std::fmt::Display) -> String {
    e.to_string()
}
fn mac(data: &[u8]) -> Option<String> {
    let bytes = data.get(..6)?;
    if bytes.iter().all(|b| *b == 0) || bytes.iter().all(|b| *b == 255) {
        return None;
    }
    Some(
        bytes
            .iter()
            .map(|b| format!("{b:02X}"))
            .collect::<Vec<_>>()
            .join(":"),
    )
}
fn allowed_service(uuid: &Uuid) -> bool {
    matches!(
        uuid.to_string().as_str(),
        "0000ae00-0000-1000-8000-00805f9b34fb"
            | "0000fd00-0000-1000-8000-00805f9b34fb"
            | "c2e6fd00-e966-1000-8000-bef9c223df6a"
            | "0000180f-0000-1000-8000-00805f9b34fb"
    )
}
fn chunk_size(mtu: u16) -> usize {
    usize::from(mtu.saturating_sub(3)).clamp(20, 512)
}

async fn stop_scan(inner: &mut Inner) {
    if let Some(scan) = inner.scan.take() {
        if let Some(task) = scan.task {
            task.abort();
        }
        if let Some(adapter) = &inner.adapter {
            let _ = adapter.stop_scan().await;
        }
    }
}

#[tauri::command]
pub async fn ble_scan(
    app: tauri::AppHandle,
    state: State<'_, Bluetooth>,
    request_id: u32,
) -> Result<(), String> {
    let mut inner = state.0.lock().await;
    stop_scan(&mut inner).await;
    if inner.connection.is_some() {
        return Err("Disconnect the current badge before searching".into());
    }
    if inner.adapter.is_none() {
        let manager = Manager::new().await.map_err(error)?;
        inner.adapter = manager.adapters().await.map_err(error)?.into_iter().next();
    }
    let adapter = inner
        .adapter
        .clone()
        .ok_or("Bluetooth adapter not found. Enable Bluetooth and allow access to E87 Studio.")?;
    let mut events = adapter.events().await.map_err(error)?;
    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(error)?;
    inner.scan = Some(Scan {
        id: request_id,
        devices: HashMap::new(),
        task: None,
    });
    let task = tauri::async_runtime::spawn(async move {
        let scan_work = async {
            while let Some(event) = events.next().await {
                let id = match event {
                    CentralEvent::DeviceDiscovered(id)
                    | CentralEvent::DeviceUpdated(id)
                    | CentralEvent::ManufacturerDataAdvertisement { id, .. } => id,
                    _ => continue,
                };
                let Ok(peripheral) = adapter.peripheral(&id).await else {
                    continue;
                };
                let Ok(Some(props)) = peripheral.properties().await else {
                    continue;
                };
                let name = props.local_name.unwrap_or_default();
                if !name.to_uppercase().starts_with("E87") {
                    continue;
                }
                let advertised_mac = props.manufacturer_data.get(&0x6db9).and_then(|v| mac(v));
                let advertised_mac = advertised_mac.or_else(|| {
                    if cfg!(target_os = "macos") {
                        None
                    } else {
                        mac(&peripheral.address().into_inner())
                    }
                });
                let device = Device {
                    device_id: id.to_string(),
                    device_name: name,
                    advertised_mac,
                    rssi: props.rssi,
                };
                let state = app.state::<Bluetooth>();
                let mut inner = state.0.lock().await;
                let Some(scan) = &mut inner.scan else { return };
                if scan.id != request_id {
                    return;
                }
                scan.devices
                    .insert(device.device_id.clone(), (peripheral, device));
                let mut devices: Vec<_> = scan.devices.values().map(|(_, d)| d.clone()).collect();
                devices.sort_by(|a, b| a.device_id.cmp(&b.device_id));
                let _ = app.emit_to(
                    "main",
                    "ble-scan",
                    ScanEvent {
                        request_id,
                        devices,
                        error: None,
                    },
                );
            }
        };
        let _ = timeout(Duration::from_secs(120), scan_work).await;
        let state = app.state::<Bluetooth>();
        let mut inner = state.0.lock().await;
        if inner.scan.as_ref().is_some_and(|s| s.id == request_id) {
            inner.scan = None;
            let _ = adapter.stop_scan().await;
            let _ = app.emit_to(
                "main",
                "ble-scan",
                ScanEvent {
                    request_id,
                    devices: vec![],
                    error: Some("Поиск завершён. Проверьте Bluetooth и попробуйте ещё раз.".into()),
                },
            );
        }
    });
    inner.scan.as_mut().unwrap().task = Some(task);
    Ok(())
}

#[tauri::command]
pub async fn ble_select(
    state: State<'_, Bluetooth>,
    request_id: u32,
    device_id: String,
) -> Result<Option<Device>, String> {
    let mut inner = state.0.lock().await;
    let scan = inner
        .scan
        .as_ref()
        .filter(|s| s.id == request_id)
        .ok_or("Search expired")?;
    let selected = if device_id.is_empty() {
        None
    } else {
        Some(
            scan.devices
                .get(&device_id)
                .cloned()
                .ok_or("Badge no longer available")?,
        )
    };
    stop_scan(&mut inner).await;
    inner.selected = selected.as_ref().map(|(p, _)| (request_id, p.clone()));
    Ok(selected.map(|(_, d)| d))
}

fn service_info(peripheral: &Peripheral) -> Vec<Service> {
    peripheral
        .services()
        .into_iter()
        .filter(|s| allowed_service(&s.uuid))
        .map(|s| Service {
            uuid: s.uuid.to_string(),
            characteristics: s
                .characteristics
                .iter()
                .map(|c| CharInfo {
                    uuid: c.uuid.to_string(),
                    properties: Properties {
                        read: c.properties.contains(CharPropFlags::READ),
                        write: c.properties.contains(CharPropFlags::WRITE),
                        write_without_response: c
                            .properties
                            .contains(CharPropFlags::WRITE_WITHOUT_RESPONSE),
                        notify: c.properties.contains(CharPropFlags::NOTIFY),
                        indicate: c.properties.contains(CharPropFlags::INDICATE),
                    },
                })
                .collect(),
        })
        .collect()
}

#[tauri::command]
pub async fn ble_connect(
    app: tauri::AppHandle,
    state: State<'_, Bluetooth>,
    session_id: u32,
) -> Result<Vec<Service>, String> {
    let mut inner = state.0.lock().await;
    let (_, peripheral) = inner
        .selected
        .as_ref()
        .filter(|(id, _)| *id == session_id)
        .ok_or("Select a badge first")?
        .clone();
    if let Some(old) = inner.connection.take() {
        let _ = old.peripheral.disconnect().await;
    }
    let result = timeout(Duration::from_secs(20), async {
        peripheral.connect().await.map_err(error)?;
        peripheral.discover_services().await.map_err(error)?;
        Ok::<_, String>(())
    })
    .await
    .map_err(|_| "Bluetooth connection timed out".to_string())
    .and_then(|r| r);
    if let Err(e) = result {
        let _ = peripheral.disconnect().await;
        return Err(e);
    }
    let mut notifications = peripheral.notifications().await.map_err(error)?;
    let conn = Arc::new(Connection {
        id: session_id,
        peripheral: peripheral.clone(),
        characteristics: peripheral
            .characteristics()
            .into_iter()
            .filter(|c| allowed_service(&c.service_uuid))
            .collect(),
        writes: Mutex::new(()),
    });
    inner.connection = Some(conn.clone());
    let services = service_info(&peripheral);
    tauri::async_runtime::spawn(async move {
        let mut tick = tokio::time::interval(Duration::from_millis(750));
        loop {
            tokio::select! {
                notification = notifications.next() => {
                    let Some(n) = notification else { break };
                    let state = app.state::<Bluetooth>();
                    if !state.0.lock().await.connection.as_ref().is_some_and(|c| Arc::ptr_eq(c, &conn)) { return; }
                    if !conn.characteristics.iter().any(|c| c.uuid == n.uuid) { continue; }
                    let _ = app.emit_to("main", "ble-notification", Notification { session_id, uuid: n.uuid.to_string(), value: n.value });
                }
                _ = tick.tick() => {
                    let state = app.state::<Bluetooth>();
                    let current = state.0.lock().await.connection.as_ref().is_some_and(|c| Arc::ptr_eq(c, &conn));
                    if !current { return; }
                    if !peripheral.is_connected().await.unwrap_or(false) { break; }
                }
            }
        }
        let state = app.state::<Bluetooth>();
        let mut inner = state.0.lock().await;
        if inner
            .connection
            .as_ref()
            .is_some_and(|c| Arc::ptr_eq(c, &conn))
        {
            inner.connection = None;
            let _ = app.emit_to("main", "ble-disconnected", session_id);
        }
    });
    Ok(services)
}

async fn connection(state: &Bluetooth, id: u32) -> Result<Arc<Connection>, String> {
    state
        .0
        .lock()
        .await
        .connection
        .clone()
        .filter(|c| c.id == id)
        .ok_or("Badge disconnected".into())
}
fn characteristic<'a>(
    conn: &'a Connection,
    service: &str,
    uuid: &str,
) -> Result<&'a Characteristic, String> {
    conn.characteristics
        .iter()
        .find(|c| c.service_uuid.to_string() == service && c.uuid.to_string() == uuid)
        .ok_or("Characteristic unavailable".into())
}
#[tauri::command]
pub async fn ble_disconnect(state: State<'_, Bluetooth>, session_id: u32) -> Result<(), String> {
    let mut inner = state.0.lock().await;
    if inner
        .connection
        .as_ref()
        .is_some_and(|c| c.id == session_id)
    {
        let conn = inner.connection.take().unwrap();
        conn.peripheral.disconnect().await.map_err(error)?;
    }
    Ok(())
}
#[tauri::command]
pub async fn ble_read(
    state: State<'_, Bluetooth>,
    session_id: u32,
    service: String,
    uuid: String,
) -> Result<Vec<u8>, String> {
    let conn = connection(&state, session_id).await?;
    let c = characteristic(&conn, &service, &uuid)?;
    timeout(Duration::from_secs(5), conn.peripheral.read(c))
        .await
        .map_err(|_| "Bluetooth read timed out")?
        .map_err(error)
}
#[tauri::command]
pub async fn ble_write(
    state: State<'_, Bluetooth>,
    session_id: u32,
    service: String,
    uuid: String,
    bytes: Vec<u8>,
    without_response: bool,
) -> Result<(), String> {
    if bytes.is_empty() || bytes.len() > 16 * 1024 {
        return Err("Invalid Bluetooth packet size".into());
    }
    let conn = connection(&state, session_id).await?;
    let c = characteristic(&conn, &service, &uuid)?;
    // Keep all fragments of a protocol frame together, including when an auto-ACK arrives.
    let _guard = conn.writes.lock().await;
    let write_type = if without_response {
        WriteType::WithoutResponse
    } else {
        WriteType::WithResponse
    };
    timeout(Duration::from_secs(10), async {
        for chunk in bytes.chunks(chunk_size(conn.peripheral.mtu())) {
            conn.peripheral
                .write(c, chunk, write_type)
                .await
                .map_err(error)?;
        }
        Ok::<_, String>(())
    })
    .await
    .map_err(|_| "Bluetooth write timed out".to_string())?
}
#[tauri::command]
pub async fn ble_notify(
    state: State<'_, Bluetooth>,
    session_id: u32,
    service: String,
    uuid: String,
    enabled: bool,
) -> Result<(), String> {
    let conn = connection(&state, session_id).await?;
    let c = characteristic(&conn, &service, &uuid)?;
    timeout(Duration::from_secs(5), async {
        if enabled {
            conn.peripheral.subscribe(c).await
        } else {
            conn.peripheral.unsubscribe(c).await
        }
    })
    .await
    .map_err(|_| "Bluetooth subscription timed out")?
    .map_err(error)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn advertising_mac_excludes_company_id() {
        assert_eq!(
            mac(&[0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0x46, 6]).as_deref(),
            Some("12:34:56:78:9A:BC")
        );
        assert!(mac(&[1, 2, 3]).is_none());
        assert!(mac(&[0; 6]).is_none());
    }
    #[test]
    fn only_badge_and_battery_services_are_exposed() {
        assert!(allowed_service(
            &Uuid::parse_str("c2e6fd00-e966-1000-8000-bef9c223df6a").unwrap()
        ));
        assert!(!allowed_service(
            &Uuid::parse_str("0000180a-0000-1000-8000-00805f9b34fb").unwrap()
        ));
    }
    #[test]
    fn frames_fit_negotiated_att_payload() {
        let frame = vec![0xfe; 503];
        let chunks: Vec<_> = frame.chunks(chunk_size(247)).collect();
        assert_eq!(
            chunks.iter().map(|c| c.len()).collect::<Vec<_>>(),
            vec![244, 244, 15]
        );
        assert_eq!(chunks.concat(), frame);
        assert_eq!(chunk_size(23), 20);
        assert_eq!(chunk_size(517), 512);
    }
}
