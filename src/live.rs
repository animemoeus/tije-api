//! Live bus feed. One poller fetches every bus from the upstream, and each
//! WebSocket client gets a filtered snapshot followed by deltas.

use std::collections::{BTreeMap, HashSet};
use std::sync::Arc;
use std::time::Duration;

use axum::{
    extract::{
        Query, State, WebSocketUpgrade,
        ws::{Message, WebSocket},
    },
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde::Deserialize;
use serde_json::{Map, Value, json};
use tokio::sync::watch;
use tokio::time::MissedTickBehavior;
use tracing::warn;

use crate::AppState;
use crate::upstream::TjClient;

// TODO: one fixed area around Monas covers the network today (Bogor, the farthest
// terminal, is 47.5 km out). Make these TJ_ settings if the network grows past it.
/// Center of the area the poller fetches.
const LAT: f64 = -6.1754;
const LON: f64 = 106.8272;
/// Radius of the area the poller fetches, and the largest radius a client may ask for.
const RADIUS_KM: f64 = 60.0;
/// Radius used when a client gives lat and lon without radius_km.
const DEFAULT_RADIUS_KM: f64 = 1.0;

/// Latest buses from the upstream, keyed by bus_body_no. A BTreeMap keeps snapshots in a stable order.
pub type Buses = BTreeMap<String, Value>;

/// The shared feed. It holds None until the first successful poll.
pub type Feed = Arc<watch::Sender<Option<Arc<Buses>>>>;

/// Polls the upstream every interval while at least one client listens, and
/// publishes the result when it differs from the last one.
pub async fn poller(client: Arc<TjClient>, feed: Feed, every: Duration) {
    let mut tick = tokio::time::interval(every);
    // A slow poll makes the next ticks late. Skip them instead of firing them back to back,
    // so the upstream never gets more than one request per interval.
    tick.set_missed_tick_behavior(MissedTickBehavior::Skip);
    loop {
        tick.tick().await;
        if feed.receiver_count() == 0 {
            continue;
        }
        match client.offline_buses(LAT, LON, RADIUS_KM).await {
            Ok(items) => {
                let buses: Buses = items
                    .into_iter()
                    .filter_map(|bus| Some((body_no(&bus)?, bus)))
                    .collect();
                feed.send_if_modified(|current| {
                    if current.as_deref() == Some(&buses) {
                        return false;
                    }
                    *current = Some(Arc::new(buses));
                    true
                });
            }
            Err(e) => warn!("bus poll failed: {e}"),
        }
    }
}

/// Query parameters of WS /ws. All of them are optional.
#[derive(Deserialize)]
pub struct WsParams {
    lat: Option<f64>,
    lon: Option<f64>,
    radius_km: Option<f64>,
    routes: Option<String>,
}

/// Which buses a client wants.
#[derive(Debug, PartialEq)]
struct Filter {
    /// Center and radius in km.
    area: Option<(f64, f64, f64)>,
    /// Upper-case route codes.
    routes: Option<HashSet<String>>,
}

impl Filter {
    /// Validates the query. lat and lon come as a pair and must lie around Jakarta,
    /// using the same bounds as the Python API.
    fn from_params(p: WsParams) -> Result<Self, String> {
        let area = match (p.lat, p.lon) {
            (Some(lat), Some(lon)) => {
                if !(-7.5..=-5.5).contains(&lat) || !(106.0..=107.5).contains(&lon) {
                    return Err("lat must be within -7.5..-5.5 and lon within 106.0..107.5".into());
                }
                let r = p.radius_km.unwrap_or(DEFAULT_RADIUS_KM);
                if !(r > 0.0 && r <= RADIUS_KM) {
                    return Err(format!("radius_km must be above 0 and at most {RADIUS_KM}"));
                }
                Some((lat, lon, r))
            }
            (None, None) if p.radius_km.is_none() => None,
            _ => return Err("lat, lon and radius_km need both lat and lon".into()),
        };
        let routes: HashSet<String> = p
            .routes
            .unwrap_or_default()
            .split(',')
            .map(|c| c.trim().to_uppercase())
            .filter(|c| !c.is_empty())
            .collect();
        Ok(Self {
            area,
            routes: (!routes.is_empty()).then_some(routes),
        })
    }

    /// Tells whether a bus passes the route and area filters.
    fn matches(&self, bus: &Value) -> bool {
        if let Some(routes) = &self.routes {
            let code = match &bus["route_code"] {
                Value::String(s) => s.to_uppercase(),
                other => other.to_string(),
            };
            if !routes.contains(&code) {
                return false;
            }
        }
        match self.area {
            None => true,
            Some((lat, lon, r)) => {
                position(bus).is_some_and(|(blat, blon)| haversine_km(lat, lon, blat, blon) <= r)
            }
        }
    }

    /// Keeps the buses that pass the filter.
    fn apply(&self, all: &Buses) -> Buses {
        all.iter()
            .filter(|(_, bus)| self.matches(bus))
            .map(|(no, bus)| (no.clone(), bus.clone()))
            .collect()
    }
}

/// Handles WS /ws. Bad parameters get a 400 before the upgrade.
pub async fn ws(
    State(state): State<AppState>,
    Query(params): Query<WsParams>,
    upgrade: WebSocketUpgrade,
) -> Response {
    match Filter::from_params(params) {
        Ok(filter) => {
            let rx = state.feed.subscribe();
            upgrade.on_upgrade(move |socket| stream(socket, rx, filter))
        }
        Err(e) => (StatusCode::BAD_REQUEST, e).into_response(),
    }
}

/// Sends one client a snapshot of its buses, then a delta every time they change,
/// until the client goes away.
async fn stream(
    mut socket: WebSocket,
    mut rx: watch::Receiver<Option<Arc<Buses>>>,
    filter: Filter,
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
                let now = filter.apply(&all);
                // The watch only keeps the latest value, so a slow client may miss
                // updates in between. Diffing against what this client was actually
                // sent keeps its view correct anyway.
                let msg = match &sent {
                    None => json!({"type": "snapshot", "buses": now.values().collect::<Vec<_>>()})
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

// TODO: every client computes its own diff, O(buses) per update. Share it between
// clients with the same filter, like the Python API's groups, if CPU becomes a problem.
/// Builds a delta message from prev to next, or None when nothing changed.
/// New buses are sent whole, known ones only with bus_body_no and the fields that changed.
fn diff(prev: &Buses, next: &Buses) -> Option<String> {
    let mut upsert = Vec::new();
    for (no, bus) in next {
        let Some(old) = prev.get(no) else {
            upsert.push(bus.clone());
            continue;
        };
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

/// Position of a bus. The route-snapped coordinates win when present, like in the app.
fn position(bus: &Value) -> Option<(f64, f64)> {
    let pick = |snap: &str, raw: &str| coord(&bus[snap]).or_else(|| coord(&bus[raw]));
    Some((
        pick("snap_latitude", "latitude")?,
        pick("snap_longitude", "longitude")?,
    ))
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

/// Great-circle distance in km, with an earth radius of 6371 km.
fn haversine_km(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let (p1, p2) = (lat1.to_radians(), lat2.to_radians());
    let (dp, dl) = (p2 - p1, (lon2 - lon1).to_radians());
    let a = (dp / 2.0).sin().powi(2) + p1.cos() * p2.cos() * (dl / 2.0).sin().powi(2);
    2.0 * 6371.0 * a.sqrt().asin()
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
            .map(|b| (body_no(b).unwrap(), b.clone()))
            .collect()
    }

    /// Parses a query string into a filter.
    fn filter(query: &str) -> Result<Filter, String> {
        let uri: axum::http::Uri = format!("/ws?{query}").parse().unwrap();
        Filter::from_params(Query::try_from_uri(&uri).unwrap().0)
    }

    /// Runs the whole app against the fake on a local port and returns the ws URL.
    async fn serve(fake: &Fake) -> (String, AppState) {
        let client = Arc::new(TjClient::new(Settings::new(start(fake).await)).unwrap());
        let state = AppState {
            client: client.clone(),
            feed: Arc::new(watch::Sender::new(None)),
        };
        tokio::spawn(poller(client, state.feed.clone(), TICK));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("ws://{}/ws", listener.local_addr().unwrap());
        let app = crate::app(state.clone());
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (url, state)
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

    /// The area filter uses the snapped position when there is one, and routes match in any case.
    #[test]
    fn filter_by_area_and_route() {
        let near = bus("NEAR", -6.1760, 106.8280, "4d");
        let mut snapped = bus("SNAP", -6.30, 106.90, "1");
        snapped["snap_latitude"] = json!("-6.1755");
        snapped["snap_longitude"] = json!(106.8273);
        let far = bus("FAR", -6.30, 106.90, "4D");
        let all = buses(&[near, snapped, far]);
        let keys = |f: Filter| f.apply(&all).into_keys().collect::<Vec<_>>();

        assert_eq!(keys(filter("").unwrap()), ["FAR", "NEAR", "SNAP"]);
        assert_eq!(
            keys(filter("lat=-6.1754&lon=106.8272").unwrap()),
            ["NEAR", "SNAP"]
        );
        assert_eq!(keys(filter("routes=4D,%20x").unwrap()), ["FAR", "NEAR"]);
        assert_eq!(
            keys(filter("lat=-6.1754&lon=106.8272&radius_km=1&routes=4d").unwrap()),
            ["NEAR"]
        );
    }

    /// lat without lon, coordinates outside Jakarta and a radius above the poll radius are rejected.
    #[test]
    fn bad_params_are_rejected() {
        assert!(filter("lat=-6.1").is_err());
        assert!(filter("radius_km=2").is_err());
        assert!(filter("lat=1&lon=106.8").is_err());
        assert!(filter("lat=-6.1&lon=106.8&radius_km=61").is_err());
        assert!(filter("lat=-6.1&lon=106.8&radius_km=0").is_err());
        assert_eq!(
            filter("lat=-6.1&lon=106.8").unwrap().area,
            Some((-6.1, 106.8, DEFAULT_RADIUS_KM))
        );
    }

    /// A client gets a filtered snapshot, then deltas with only the changes, and nothing when nothing changed.
    #[tokio::test]
    async fn snapshot_then_deltas() {
        let f = fake();
        f.lock().unwrap().buses = vec![
            bus("A", -6.1760, 106.8280, "1"),
            bus("FAR", -6.30, 106.90, "1"),
        ];
        let (url, _) = serve(&f).await;
        let mut ws = connect(&format!("{url}?lat=-6.1754&lon=106.8272&radius_km=1")).await;

        let snap = next(&mut ws).await;
        assert_eq!(snap["type"], "snapshot");
        assert_eq!(nos(&snap), ["A"]);
        silent(&mut ws).await;

        f.lock().unwrap().buses[0]["speed"] = json!(20);
        assert_eq!(
            next(&mut ws).await,
            json!({"type": "delta", "upsert": [{"bus_body_no": "A", "speed": 20}], "remove": []})
        );

        // Moving out of the radius counts as a removal.
        f.lock().unwrap().buses[0]["latitude"] = json!(-6.30);
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

    /// Two clients with different filters share one poller but get different buses.
    #[tokio::test]
    async fn clients_share_the_poll() {
        let f = fake();
        f.lock().unwrap().buses = vec![
            bus("A", -6.1760, 106.8280, "1"),
            bus("B", -6.30, 106.90, "2"),
        ];
        let (url, state) = serve(&f).await;
        let mut all = connect(&url).await;
        let mut route2 = connect(&format!("{url}?routes=2")).await;
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

    /// Bad parameters get a 400 instead of a WebSocket.
    #[tokio::test]
    async fn bad_params_get_400() {
        let (url, _) = serve(&fake()).await;
        match connect_async(format!("{url}?lat=-6.1")).await {
            Err(tungstenite::Error::Http(resp)) => assert_eq!(resp.status(), 400),
            other => panic!("expected HTTP 400, got {other:?}"),
        }
    }
}
