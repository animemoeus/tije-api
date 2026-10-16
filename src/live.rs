//! Live bus feed. One poller fetches every bus from the upstream. WebSocket clients
//! get a snapshot of the routes they pick followed by deltas, and an event stream
//! follows a single bus.

use std::collections::{BTreeMap, HashSet};
use std::sync::Arc;
use std::time::Duration;

use axum::{
    extract::{
        Path, Query, State, WebSocketUpgrade,
        ws::{Message, WebSocket},
    },
    response::{
        Response,
        sse::{Event, KeepAlive, Sse},
    },
};
use futures_util::Stream;
use serde::Deserialize;
use serde_json::{Map, Value, json};
use tokio::sync::watch;
use tokio::time::MissedTickBehavior;
use tracing::warn;

use crate::AppState;
use crate::upstream::TjClient;

// TODO: one fixed area around Monas covers the network today (the farthest bus,
// near Bogor, is 47.7 km out). Make these TJ_ settings if the network grows past it.
/// Center of the area the poller fetches.
const LAT: f64 = -6.1754;
const LON: f64 = 106.8272;
/// Radius of the area the poller fetches.
const RADIUS_KM: f64 = 60.0;

/// Latest buses from the upstream, keyed by bus_body_no. A BTreeMap keeps snapshots in a stable order.
/// Each bus sits behind an Arc, so clients share one copy and an unchanged bus keeps the same pointer.
pub type Buses = BTreeMap<String, Arc<Value>>;

/// The shared feed. It holds None until the first successful poll.
pub type Feed = Arc<watch::Sender<Option<Arc<Buses>>>>;

/// Polls the upstream every interval while at least one client listens, and
/// publishes the result when it differs from the last one.
pub async fn poller(client: Arc<TjClient>, feed: Feed, every: Duration) {
    let mut tick = tokio::time::interval(every);
    // A slow poll makes the next ticks late. Skip them instead of firing them back to back,
    // so the upstream never gets more than one request at a time.
    tick.set_missed_tick_behavior(MissedTickBehavior::Skip);
    loop {
        tick.tick().await;
        if feed.receiver_count() == 0 {
            continue;
        }
        match client.offline_buses(LAT, LON, RADIUS_KM).await {
            Ok(items) => {
                let fresh = items
                    .into_iter()
                    .filter_map(|bus| Some((body_no(&bus)?, enrich(bus))));
                feed.send_if_modified(|current| match merge(current.as_deref(), fresh) {
                    Some(buses) => {
                        *current = Some(Arc::new(buses));
                        true
                    }
                    None => false,
                });
            }
            Err(e) => warn!("bus poll failed: {e}"),
        }
    }
}

/// Builds the next feed from a fresh poll, or returns None when nothing changed.
/// A bus equal to its previous version keeps the old Arc, which lets diff skip it
/// with a pointer check instead of comparing every field again for every client.
fn merge(prev: Option<&Buses>, fresh: impl IntoIterator<Item = (String, Value)>) -> Option<Buses> {
    let mut changed = false;
    let next: Buses = fresh
        .into_iter()
        .map(|(no, bus)| {
            let bus = match prev.and_then(|p| p.get(&no)) {
                Some(old) if **old == bus => old.clone(),
                _ => {
                    changed = true;
                    Arc::new(bus)
                }
            };
            (no, bus)
        })
        .collect();
    // A bus that left the feed creates no new Arc, so a shorter map is the only sign of it.
    (changed || prev.is_none_or(|p| p.len() != next.len())).then_some(next)
}

/// Adds the fields the frontend reads, the same ones the Python API derives, and
/// keeps every upstream field as it is.
///
/// raw_latitude and raw_longitude hold the reported position, latitude and longitude
/// the route-snapped one when the upstream has it. type becomes BRT, Mikrotrans or
/// Non-BRT, and next_stop_name and prev_stop_name drop the stop code prefix.
fn enrich(mut bus: Value) -> Value {
    let Some(fields) = bus.as_object_mut() else {
        return bus;
    };
    let raw_lat = fields.get("latitude").cloned().unwrap_or(Value::Null);
    let raw_lon = fields.get("longitude").cloned().unwrap_or(Value::Null);
    let snapped = |snap: &str, raw: &Value| {
        fields
            .get(snap)
            .and_then(coord)
            .or_else(|| coord(raw))
            .map_or(Value::Null, Value::from)
    };
    let (lat, lon) = (
        snapped("snap_latitude", &raw_lat),
        snapped("snap_longitude", &raw_lon),
    );
    let kind = bus_type(fields.get("type"));
    let next = stop_name(fields.get("next_stops"));
    let prev = stop_name(fields.get("prev_stops"));
    fields.insert("raw_latitude".into(), raw_lat);
    fields.insert("raw_longitude".into(), raw_lon);
    fields.insert("latitude".into(), lat);
    fields.insert("longitude".into(), lon);
    fields.insert("type".into(), kind.into());
    fields.insert("next_stop_name".into(), next.into());
    fields.insert("prev_stop_name".into(), prev.into());
    bus
}

/// Maps the upstream bus type to BRT, Mikrotrans or Non-BRT, ignoring case.
fn bus_type(raw: Option<&Value>) -> &'static str {
    match raw
        .and_then(Value::as_str)
        .map(str::to_uppercase)
        .as_deref()
    {
        Some("BRT") => "BRT",
        Some("MIKROTRANS") => "Mikrotrans",
        _ => "Non-BRT",
    }
}

/// Strips the stop code the upstream puts in front of halte names, so
/// "H00251P-Tosari" becomes "Tosari". Only a prefix that starts with a letter
/// followed by a digit counts as a code.
fn stop_name(raw: Option<&Value>) -> Option<String> {
    let s = match raw? {
        Value::String(s) if !s.is_empty() => s.as_str(),
        _ => return None,
    };
    let Some((code, name)) = s.split_once('-') else {
        return Some(s.to_owned());
    };
    let mut chars = code.chars();
    let is_code = chars.next().is_some_and(char::is_alphabetic)
        && chars.next().is_some_and(|c| c.is_ascii_digit());
    Some(if is_code { name } else { s }.to_owned())
}

/// Query parameters of WS /ws. Anything else in the query, such as the lat, lon,
/// radius_km and mode the old frontend sends, is ignored.
#[derive(Deserialize)]
pub struct WsParams {
    /// Comma-separated route codes. Empty or missing means every route.
    routes: Option<String>,
}

/// Upper-case route codes a client wants, or None for every route.
type Routes = Option<HashSet<String>>;

/// Parses the routes parameter. Codes match without regard to case.
fn parse_routes(raw: Option<&str>) -> Routes {
    let codes: HashSet<String> = raw
        .unwrap_or_default()
        .split(',')
        .map(|c| c.trim().to_uppercase())
        .filter(|c| !c.is_empty())
        .collect();
    (!codes.is_empty()).then_some(codes)
}

/// Keeps the buses on the wanted routes.
fn apply(routes: &Routes, all: &Buses) -> Buses {
    all.iter()
        .filter(|(_, bus)| {
            routes.as_ref().is_none_or(|r| {
                let code = match &bus["route_code"] {
                    Value::String(s) => s.to_uppercase(),
                    other => other.to_string(),
                };
                r.contains(&code)
            })
        })
        .map(|(no, bus)| (no.clone(), bus.clone()))
        .collect()
}

/// Handles WS /ws.
pub async fn ws(
    State(state): State<AppState>,
    Query(params): Query<WsParams>,
    upgrade: WebSocketUpgrade,
) -> Response {
    let routes = parse_routes(params.routes.as_deref());
    let rx = state.feed.subscribe();
    upgrade.on_upgrade(move |socket| stream(socket, rx, routes))
}

/// Sends one client a snapshot of its buses, then a delta every time they change,
/// until the client goes away.
async fn stream(
    mut socket: WebSocket,
    mut rx: watch::Receiver<Option<Arc<Buses>>>,
    routes: Routes,
) {
    // What this client has been sent so far. None until the snapshot goes out.
    let mut sent: Option<Buses> = None;
    // Treat the current value as new, so a client that joins after the first poll
    // gets its snapshot right away.
    rx.mark_changed();
    loop {
        tokio::select! {
            changed = rx.changed() => {
                if changed.is_err() {
                    break;
                }
                let Some(all) = rx.borrow_and_update().clone() else {
                    continue;
                };
                let now = apply(&routes, &all);
                // The watch only keeps the latest value, so a slow client may miss
                // updates in between. Diffing against what this client was actually
                // sent keeps its view correct anyway.
                let msg = match &sent {
                    None => json!({"type": "snapshot", "buses": now.values().map(Arc::as_ref).collect::<Vec<_>>()})
                        .to_string(),
                    Some(prev) => match diff(prev, &now) {
                        Some(msg) => msg,
                        None => continue,
                    },
                };
                if socket.send(Message::text(msg)).await.is_err() {
                    break;
                }
                sent = Some(now);
            }
            msg = socket.recv() => {
                if matches!(msg, None | Some(Err(_)) | Some(Ok(Message::Close(_)))) {
                    break;
                }
            }
        }
    }
}

/// Handles GET /buses/{bus_body_no} as a server-sent event stream.
///
/// A bus event carries the whole bus, first as soon as there is data and then each
/// time the bus changes. A gone event says the bus is missing from the latest poll,
/// and the stream ends after it. The stream listens to the shared feed, so it keeps
/// the poller running and never calls the upstream itself.
pub async fn bus_events(
    State(state): State<AppState>,
    Path(no): Path<String>,
) -> Sse<impl Stream<Item = Result<Event, axum::Error>>> {
    let mut rx = state.feed.subscribe();
    rx.mark_changed();
    // The state is the receiver plus the last bus sent. None ends the stream.
    let events = futures_util::stream::unfold(Some((rx, None::<Arc<Value>>)), move |st| {
        let no = no.clone();
        async move {
            let (mut rx, last) = st?;
            loop {
                rx.changed().await.ok()?;
                let Some(all) = rx.borrow_and_update().clone() else {
                    continue;
                };
                let Some(bus) = all.get(&no) else {
                    let gone = Event::default()
                        .event("gone")
                        .json_data(json!({ "bus_body_no": no }));
                    return Some((gone, None));
                };
                if last.as_ref() != Some(bus) {
                    let event = Event::default().event("bus").json_data(bus.as_ref());
                    return Some((event, Some((rx, Some(bus.clone())))));
                }
            }
        }
    });
    Sse::new(events).keep_alive(KeepAlive::new().interval(Duration::from_secs(15)))
}

/// Builds a delta message from prev to next, or None when nothing changed.
/// New buses are sent whole, known ones only with bus_body_no and the fields that changed.
fn diff(prev: &Buses, next: &Buses) -> Option<String> {
    let mut upsert = Vec::new();
    for (no, bus) in next {
        let Some(old) = prev.get(no) else {
            upsert.push(bus.as_ref().clone());
            continue;
        };
        // merge keeps the Arc of an unchanged bus, so the same pointer means the same data.
        if Arc::ptr_eq(old, bus) {
            continue;
        }
        let (Some(new_fields), Some(old_fields)) = (bus.as_object(), old.as_object()) else {
            continue;
        };
        let mut changed: Map<String, Value> = new_fields
            .iter()
            .filter(|(k, v)| old_fields.get(*k) != Some(*v))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        if !changed.is_empty() {
            changed.insert("bus_body_no".into(), no.as_str().into());
            upsert.push(Value::Object(changed));
        }
    }
    let remove: Vec<&String> = prev.keys().filter(|no| !next.contains_key(*no)).collect();
    if upsert.is_empty() && remove.is_empty() {
        return None;
    }
    Some(json!({"type": "delta", "upsert": upsert, "remove": remove}).to_string())
}

/// Reads bus_body_no as a string. The upstream sends strings, but a number is accepted too.
fn body_no(bus: &Value) -> Option<String> {
    match bus.get("bus_body_no")? {
        Value::String(s) if !s.is_empty() => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

/// Reads a coordinate sent as a number or a numeric string. Zero counts as missing,
/// as it does in the Python API.
fn coord(v: &Value) -> Option<f64> {
    let x = match v {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.parse().ok(),
        _ => None,
    }?;
    (x != 0.0).then_some(x)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Settings;
    use crate::upstream::fake::{Fake, count, fake, start};
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::{MaybeTlsStream, WebSocketStream, connect_async, tungstenite};

    type Client = WebSocketStream<MaybeTlsStream<tokio::net::TcpStream>>;

    /// Poll interval used by the end to end tests.
    const TICK: Duration = Duration::from_millis(30);

    /// A bus as the upstream sends it.
    fn bus(no: &str, lat: f64, lon: f64, route: &str) -> Value {
        json!({"bus_body_no": no, "latitude": lat, "longitude": lon, "route_code": route, "speed": 0})
    }

    /// Turns a list of buses into the map the feed holds.
    fn buses(items: &[Value]) -> Buses {
        items
            .iter()
            .map(|b| (body_no(b).unwrap(), Arc::new(b.clone())))
            .collect()
    }

    /// Runs the whole app against the fake on a local port and returns its base address.
    async fn serve(fake: &Fake) -> (String, AppState) {
        let state = AppState::new(TjClient::new(Settings::new(start(fake).await)).unwrap());
        tokio::spawn(poller(state.client.clone(), state.feed.clone(), TICK));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap().to_string();
        let app = crate::app(state.clone());
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (addr, state)
    }

    /// Opens a WebSocket connection.
    async fn connect(url: &str) -> Client {
        connect_async(url).await.unwrap().0
    }

    /// Waits up to one second for the next message and parses it.
    async fn next(ws: &mut Client) -> Value {
        let msg = tokio::time::timeout(Duration::from_secs(1), ws.next())
            .await
            .expect("no message within a second")
            .unwrap()
            .unwrap();
        serde_json::from_str(msg.to_text().unwrap()).unwrap()
    }

    /// Asserts that nothing arrives for a few poll intervals.
    async fn silent(ws: &mut Client) {
        let r = tokio::time::timeout(TICK * 5, ws.next()).await;
        assert!(r.is_err(), "unexpected message: {r:?}");
    }

    /// Lists the bus_body_no values in a snapshot.
    fn nos(msg: &Value) -> Vec<&str> {
        msg["buses"]
            .as_array()
            .unwrap()
            .iter()
            .map(|b| b["bus_body_no"].as_str().unwrap())
            .collect()
    }

    /// New buses come whole, changed ones with only their changed fields, and gone ones in remove.
    #[test]
    fn diff_sends_only_changes() {
        let a = bus("A", -6.1, 106.8, "1");
        let b = bus("B", -6.2, 106.8, "1");
        let prev = buses(&[a.clone(), b]);
        let mut moved = a.clone();
        moved["latitude"] = json!(-6.11);
        let c = bus("C", -6.3, 106.8, "2");
        let msg: Value =
            serde_json::from_str(&diff(&prev, &buses(&[moved, c.clone()])).unwrap()).unwrap();
        assert_eq!(msg["type"], "delta");
        assert_eq!(
            msg["upsert"],
            json!([{"bus_body_no": "A", "latitude": -6.11}, c])
        );
        assert_eq!(msg["remove"], json!(["B"]));
        assert_eq!(diff(&prev, &prev), None);
    }

    /// merge keeps the Arc of an unchanged bus, gives a changed one a new Arc, and
    /// reports a removed bus or a repeat poll correctly.
    #[test]
    fn merge_reuses_unchanged_buses() {
        let a = bus("A", -6.1, 106.8, "1");
        let b = bus("B", -6.2, 106.8, "1");
        let pairs = |items: &[&Value]| {
            items
                .iter()
                .map(|v| (body_no(v).unwrap(), (*v).clone()))
                .collect::<Vec<_>>()
        };
        let first = merge(None, pairs(&[&a, &b])).unwrap();
        assert_eq!(merge(Some(&first), pairs(&[&a, &b])), None);

        let mut moved = b.clone();
        moved["latitude"] = json!(-6.21);
        let second = merge(Some(&first), pairs(&[&a, &moved])).unwrap();
        assert!(Arc::ptr_eq(&first["A"], &second["A"]));
        assert!(!Arc::ptr_eq(&first["B"], &second["B"]));
        assert_eq!(*second["B"], moved);

        let third = merge(Some(&second), pairs(&[&a])).unwrap();
        assert_eq!(third.keys().collect::<Vec<_>>(), ["A"]);
        assert_eq!(merge(None, pairs(&[])), Some(Buses::new()));
    }

    /// enrich derives the frontend fields and keeps the upstream ones.
    #[test]
    fn enrich_adds_frontend_fields() {
        let mut b = bus("A", -6.2, 106.8, "1");
        b["type"] = json!("brt");
        b["snap_latitude"] = json!("-6.21");
        b["next_stops"] = json!("H00251P-Tosari");
        b["prev_stops"] = json!("Bundaran HI-Astra");
        let e = enrich(b);
        assert_eq!(e["raw_latitude"], -6.2);
        assert_eq!(e["latitude"], -6.21);
        assert_eq!(e["raw_longitude"], 106.8);
        assert_eq!(e["longitude"], 106.8);
        assert_eq!(e["type"], "BRT");
        assert_eq!(e["next_stop_name"], "Tosari");
        assert_eq!(e["prev_stop_name"], "Bundaran HI-Astra");
        assert_eq!(e["next_stops"], "H00251P-Tosari");
        assert_eq!(e["speed"], 0);

        let e = enrich(json!({"bus_body_no": "B", "type": "Mikrotrans"}));
        assert_eq!(e["type"], "Mikrotrans");
        assert_eq!(e["latitude"], Value::Null);
        assert_eq!(e["next_stop_name"], Value::Null);
        assert_eq!(enrich(json!({"type": "other"}))["type"], "Non-BRT");
    }

    /// routes takes many codes, trims them and matches without regard to case.
    #[test]
    fn filter_by_routes() {
        let all = buses(&[
            bus("A", -6.1, 106.8, "4d"),
            bus("B", -6.1, 106.8, "1"),
            bus("C", -6.1, 106.8, "JAK.10"),
        ]);
        let keys = |raw: Option<&str>| {
            apply(&parse_routes(raw), &all)
                .into_keys()
                .collect::<Vec<_>>()
        };
        assert_eq!(keys(None), ["A", "B", "C"]);
        assert_eq!(keys(Some(" ,")), ["A", "B", "C"]);
        assert_eq!(keys(Some("4D, jak.10")), ["A", "C"]);
        assert_eq!(keys(Some("9")), Vec::<String>::new());
    }

    /// A client gets a snapshot of its routes, then deltas with only the changes,
    /// and nothing when nothing changed.
    #[tokio::test]
    async fn snapshot_then_deltas() {
        let f = fake();
        f.lock().unwrap().buses = vec![
            bus("A", -6.1760, 106.8280, "1"),
            bus("B", -6.30, 106.90, "2"),
        ];
        let (addr, _) = serve(&f).await;
        let mut ws = connect(&format!("ws://{addr}/ws?routes=1")).await;

        let snap = next(&mut ws).await;
        assert_eq!(snap["type"], "snapshot");
        assert_eq!(nos(&snap), ["A"]);
        assert_eq!(snap["buses"][0]["raw_latitude"], -6.1760);
        silent(&mut ws).await;

        f.lock().unwrap().buses[0]["speed"] = json!(20);
        assert_eq!(
            next(&mut ws).await,
            json!({"type": "delta", "upsert": [{"bus_body_no": "A", "speed": 20}], "remove": []})
        );

        // A new position shows up in both the shown and the raw coordinates.
        f.lock().unwrap().buses[0]["latitude"] = json!(-6.1770);
        assert_eq!(
            next(&mut ws).await,
            json!({"type": "delta", "upsert": [{"bus_body_no": "A", "latitude": -6.1770, "raw_latitude": -6.1770}], "remove": []})
        );

        // A bus that leaves the upstream data is removed.
        f.lock().unwrap().buses.remove(0);
        assert_eq!(
            next(&mut ws).await,
            json!({"type": "delta", "upsert": [], "remove": ["A"]})
        );

        // The poller fetched the fixed area around Monas.
        let s = f.lock().unwrap();
        let poll = s.calls.iter().find(|c| c.0 == "/v1/bus/offline").unwrap();
        assert_eq!(
            poll.1,
            json!({"latitude": LAT, "longitude": LON, "radius": RADIUS_KM, "event": "change_loc"})
        );
    }

    /// The area parameters the old frontend sends are ignored instead of rejected.
    #[tokio::test]
    async fn old_area_params_are_ignored() {
        let f = fake();
        f.lock().unwrap().buses = vec![bus("FAR", -6.60, 106.80, "1")];
        let (addr, _) = serve(&f).await;
        let mut ws = connect(&format!(
            "ws://{addr}/ws?lat=-6.1754&lon=106.8272&radius_km=1&mode=delta"
        ))
        .await;
        assert_eq!(nos(&next(&mut ws).await), ["FAR"]);
    }

    /// Two clients with different filters share one poller but get different buses.
    #[tokio::test]
    async fn clients_share_the_poll() {
        let f = fake();
        f.lock().unwrap().buses = vec![
            bus("A", -6.1760, 106.8280, "1"),
            bus("B", -6.30, 106.90, "2"),
        ];
        let (addr, state) = serve(&f).await;
        let mut all = connect(&format!("ws://{addr}/ws")).await;
        let mut route2 = connect(&format!("ws://{addr}/ws?routes=2")).await;
        assert_eq!(nos(&next(&mut all).await), ["A", "B"]);
        assert_eq!(nos(&next(&mut route2).await), ["B"]);
        assert_eq!(state.feed.receiver_count(), 2);

        // One poller means at most one poll per tick, however many clients listen.
        let before = count(&f, "/v1/bus/offline");
        tokio::time::sleep(TICK * 10).await;
        let polls = count(&f, "/v1/bus/offline") - before;
        assert!(polls <= 11, "{polls} polls in 10 ticks");
        all.close(None).await.unwrap();
        route2
            .send(tungstenite::Message::Close(None))
            .await
            .unwrap();
    }

    /// With nobody listening, the poller leaves the upstream alone.
    #[tokio::test]
    async fn no_polls_without_clients() {
        let f = fake();
        serve(&f).await;
        tokio::time::sleep(TICK * 5).await;
        assert!(f.lock().unwrap().calls.is_empty());
    }

    /// Reads server-sent events from a response body, one (event, data) pair at a time.
    struct Events {
        body: reqwest::Response,
        buf: String,
    }

    impl Events {
        /// Opens GET /buses/{no} and checks the content type.
        async fn open(addr: &str, no: &str) -> Self {
            let body = reqwest::get(format!("http://{addr}/buses/{no}"))
                .await
                .unwrap();
            assert_eq!(body.headers()["content-type"], "text/event-stream");
            Self {
                body,
                buf: String::new(),
            }
        }

        /// Waits up to one second for the next event. None means the stream ended.
        async fn next(&mut self) -> Option<(String, Value)> {
            loop {
                // Events end with a blank line. Keep-alive comments start with a colon.
                if let Some(end) = self.buf.find("\n\n") {
                    let block: String = self.buf.drain(..end + 2).collect();
                    let field = |name: &str| {
                        block
                            .lines()
                            .find_map(|l| l.strip_prefix(name))
                            .map(str::to_owned)
                    };
                    if let (Some(event), Some(data)) = (field("event: "), field("data: ")) {
                        return Some((event, serde_json::from_str(&data).unwrap()));
                    }
                    continue;
                }
                let chunk = tokio::time::timeout(Duration::from_secs(1), self.body.chunk())
                    .await
                    .expect("no event within a second")
                    .unwrap()?;
                self.buf.push_str(std::str::from_utf8(&chunk).unwrap());
            }
        }
    }

    /// The bus stream sends the bus, then each change to it, ignores other buses,
    /// and ends with gone once the bus disappears.
    #[tokio::test]
    async fn bus_events_follow_one_bus() {
        let f = fake();
        f.lock().unwrap().buses = vec![
            bus("A", -6.1760, 106.8280, "1"),
            bus("B", -6.30, 106.90, "2"),
        ];
        let (addr, _) = serve(&f).await;
        // The stream alone keeps the poller running, with no WebSocket client.
        let mut ev = Events::open(&addr, "A").await;

        let (name, data) = ev.next().await.unwrap();
        assert_eq!(name, "bus");
        assert_eq!(data["bus_body_no"], "A");
        assert_eq!(data["type"], "Non-BRT");
        assert_eq!(data["raw_latitude"], -6.1760);

        // A change to another bus sends nothing, a change to this one sends it again.
        f.lock().unwrap().buses[1]["speed"] = json!(5);
        tokio::time::sleep(TICK * 4).await;
        f.lock().unwrap().buses[0]["speed"] = json!(30);
        let (name, data) = ev.next().await.unwrap();
        assert_eq!((name.as_str(), &data["speed"]), ("bus", &json!(30)));

        f.lock().unwrap().buses.remove(0);
        assert_eq!(
            ev.next().await,
            Some(("gone".into(), json!({"bus_body_no": "A"})))
        );
        assert_eq!(ev.next().await, None);
    }

    /// An unknown bus gets gone right after the first poll.
    #[tokio::test]
    async fn bus_events_unknown_bus() {
        let f = fake();
        f.lock().unwrap().buses = vec![bus("A", -6.1760, 106.8280, "1")];
        let (addr, _) = serve(&f).await;
        let mut ev = Events::open(&addr, "NOPE").await;
        assert_eq!(ev.next().await.unwrap().0, "gone");
        assert_eq!(ev.next().await, None);
    }
}
