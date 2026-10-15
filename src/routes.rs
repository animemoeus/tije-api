//! Route types and geometry for the map, from GET /v2/route and GET /v2/route/{code}.
//!
//! A route detail holds route (name and colours) and up to three directions,
//! outbound, inbound and loop, each null when absent. A direction has a trip_id (the
//! same format as a bus's trip_id), a headsign, its stops in travel order and a
//! Google encoded polyline with 5 decimal places.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use axum::{
    Json,
    extract::{Query, State},
};
use futures_util::{StreamExt, stream};
use serde::Deserialize;
use serde_json::{Value, json};
use tracing::warn;

use crate::upstream::UpstreamError;
use crate::{AppError, AppState};

/// Route types as the upstream names them in route_desc, in the order GET /route-types lists them.
const ROUTE_TYPES: [&str; 7] = [
    "BRT",
    "Angkutan Umum Integrasi",
    "Mikrotrans",
    "Transjabodetabek",
    "Royaltrans",
    "Rusun",
    "Bus Wisata",
];

/// Route data rarely changes, so the list and each detail are kept this long.
const CACHE_TTL: Duration = Duration::from_secs(3600);

/// How many route details are fetched from the upstream at the same time.
const CONCURRENCY: usize = 5;

/// Cache key of the route list. Route codes never contain spaces, so it cannot clash with one.
const LIST_KEY: &str = "route list";

/// Upstream route data by key, with the time it was fetched. A Null value marks a
/// route that does not exist or has no path, so it is not asked for again.
pub type RouteCache = Mutex<HashMap<String, (Instant, Value)>>;

/// Handles GET /route-types: every route type with the number of routes the upstream has of it.
pub async fn route_types(State(state): State<AppState>) -> Result<Json<Value>, AppError> {
    let list = route_list(&state).await?;
    let types: Vec<Value> = ROUTE_TYPES
        .iter()
        .map(|t| {
            let n = list.iter().filter(|r| is_type(r, t)).count();
            json!({ "type": t, "routes": n })
        })
        .collect();
    Ok(Json(json!({ "types": types })))
}

/// Query parameters of GET /routes.
#[derive(Deserialize)]
pub struct RoutesParams {
    /// Comma-separated route types. Empty or missing means every route.
    r#type: Option<String>,
}

/// Handles GET /routes: path and stops of every route of the given types, sorted
/// by route code. Routes whose detail fails or has no path are left out.
pub async fn routes(
    State(state): State<AppState>,
    Query(params): Query<RoutesParams>,
) -> Result<Json<Value>, AppError> {
    let types = parse_types(params.r#type.as_deref().unwrap_or_default())?;
    let list = route_list(&state).await?;
    let codes: Vec<String> = list
        .iter()
        .filter(|r| types.is_empty() || types.iter().any(|t| is_type(r, t)))
        .filter_map(|r| text(&r["route_short_name"]).or_else(|| text(&r["route_id"])))
        .collect();
    let mut found: Vec<Value> = stream::iter(codes)
        .map(|code| route_detail(&state, code))
        .buffer_unordered(CONCURRENCY)
        .filter_map(|r| async { r })
        .collect()
        .await;
    found.sort_by_cached_key(|r| natural_key(r["route_code"].as_str().unwrap_or_default()));
    Ok(Json(json!({ "types": types, "routes": found })))
}

/// Splits the type parameter and maps each entry to its canonical name, ignoring
/// case. Any unknown type is a bad request.
fn parse_types(raw: &str) -> Result<Vec<&'static str>, AppError> {
    let mut types = Vec::new();
    for t in raw.split(',').map(str::trim).filter(|t| !t.is_empty()) {
        let known = ROUTE_TYPES
            .iter()
            .find(|k| k.eq_ignore_ascii_case(t))
            .ok_or_else(|| {
                AppError::BadRequest(format!(
                    "unknown route type {t:?}, expected some of {ROUTE_TYPES:?}"
                ))
            })?;
        if !types.contains(known) {
            types.push(*known);
        }
    }
    Ok(types)
}

/// Tells whether a route from the list has the given type.
fn is_type(route: &Value, t: &str) -> bool {
    route["route_desc"]
        .as_str()
        .is_some_and(|d| d.trim().eq_ignore_ascii_case(t))
}

/// The route list, from the cache when it is fresh.
async fn route_list(state: &AppState) -> Result<Vec<Value>, UpstreamError> {
    let list = cached(&state.routes, LIST_KEY, async {
        Ok(Value::Array(state.client.list_routes().await?))
    })
    .await?;
    Ok(match list {
        Value::Array(items) => items,
        _ => Vec::new(),
    })
}

/// One normalized route, from the cache when it is fresh. None when the route does
/// not exist, has no path, or the upstream fails; each case is logged.
async fn route_detail(state: &AppState, code: String) -> Option<Value> {
    let code = code.trim().to_uppercase();
    let fetch = async {
        match state.client.get_route(&code).await {
            Ok(data) => {
                let route = normalize_route(&code, &data);
                let has_path = route["directions"]
                    .as_array()
                    .is_some_and(|d| !d.is_empty());
                Ok(if has_path { route } else { Value::Null })
            }
            Err(e) if e.status() == Some(404) => Ok(Value::Null),
            Err(e) => Err(e),
        }
    };
    match cached(&state.routes, &code, fetch).await {
        Ok(Value::Null) => {
            warn!("route {code} skipped: not found or no path");
            None
        }
        Ok(route) => Some(route),
        Err(e) => {
            warn!("route {code} skipped: {e}");
            None
        }
    }
}

// TODO: two requests that miss the cache at the same time both fetch the same data.
// Add single-flight per key if cold starts turn out to load the upstream too much.
/// Returns the cached value for key while it is fresh, or runs fetch and caches its
/// result. Errors are not cached.
async fn cached(
    cache: &RouteCache,
    key: &str,
    fetch: impl Future<Output = Result<Value, UpstreamError>>,
) -> Result<Value, UpstreamError> {
    if let Some((at, value)) = cache.lock().expect("route cache lock poisoned").get(key)
        && at.elapsed() < CACHE_TTL
    {
        return Ok(value.clone());
    }
    let value = fetch.await?;
    cache
        .lock()
        .expect("route cache lock poisoned")
        .insert(key.to_owned(), (Instant::now(), value.clone()));
    Ok(value)
}

/// Turns an upstream route detail into {route_code, route_name, route_type, colours,
/// directions: [{direction, trip_id, headsign, path, stops}]}, the shape the Python
/// API returns. A direction without a polyline gets straight lines between its stops.
pub fn normalize_route(code: &str, data: &Value) -> Value {
    let route = &data["route"];
    let directions: Vec<Value> = ["outbound", "inbound", "loop"]
        .into_iter()
        .filter(|name| data[*name].is_object())
        .map(|name| {
            let d = &data[name];
            let stops: Vec<Value> = d["stops"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|s| !s["stop_lat"].is_null() && !s["stop_lon"].is_null())
                .map(|s| {
                    json!({
                        "stop_id": s["stop_id"],
                        "name": s["stop_name"],
                        "lat": s["stop_lat"],
                        "lon": s["stop_lon"],
                        "type": s["bus_stop_type"],
                    })
                })
                .collect();
            let mut path: Vec<Value> = d["polyline"]
                .as_str()
                .map(decode_polyline)
                .unwrap_or_default()
                .into_iter()
                .map(|p| json!(p))
                .collect();
            if path.len() < 2 {
                path = stops.iter().map(|s| json!([s["lat"], s["lon"]])).collect();
            }
            json!({
                "direction": name,
                "trip_id": d["trip_id"],
                "headsign": d["headsign"],
                "path": path,
                "stops": stops,
            })
        })
        .collect();
    let route_code = text(&route["route_short_name"])
        .or_else(|| text(&route["route_id"]))
        .unwrap_or_else(|| code.to_owned());
    json!({
        "route_code": route_code,
        "route_name": route["route_long_name"],
        "route_type": route["route_desc"],
        "route_color": route["route_color"],
        "route_text_color": route["route_text_color"],
        "directions": directions,
    })
}

/// Decodes a Google encoded polyline with 5 decimal places into [lat, lon] points,
/// rounded to 6 decimals. Truncated input keeps the points decoded so far.
pub fn decode_polyline(encoded: &str) -> Vec<[f64; 2]> {
    let bytes = encoded.as_bytes();
    // Each number is a zigzag-encoded varint: 5-bit chunks offset by 63, where a
    // chunk below 0x20 is the last one. A point is a lat delta then a lon delta.
    let number = |i: &mut usize| -> Option<i64> {
        let (mut result, mut shift) = (0i64, 0);
        loop {
            let b = i64::from(*bytes.get(*i)?) - 63;
            *i += 1;
            if shift > 60 {
                return None;
            }
            result |= (b & 0x1f) << shift;
            shift += 5;
            if b < 0x20 {
                break;
            }
        }
        Some(if result & 1 == 1 {
            !(result >> 1)
        } else {
            result >> 1
        })
    };
    let round = |x: i64| (x as f64 / 1e5 * 1e6).round() / 1e6;
    let (mut i, mut lat, mut lon) = (0, 0i64, 0i64);
    let mut out = Vec::new();
    while i < bytes.len() {
        let (Some(dlat), Some(dlon)) = (number(&mut i), number(&mut i)) else {
            break;
        };
        lat += dlat;
        lon += dlon;
        out.push([round(lat), round(lon)]);
    }
    out
}

/// Sort key that puts route codes in natural order: 1, 1A, 2, 4D, 10, JAK.10.
/// Digit runs compare as numbers and sort before text runs, as in the Python API.
fn natural_key(code: &str) -> Vec<(u8, u64, String)> {
    let mut parts = Vec::new();
    let mut rest = code;
    while let Some(c) = rest.chars().next() {
        let digit = c.is_ascii_digit();
        let end = rest
            .find(|ch: char| ch.is_ascii_digit() != digit)
            .unwrap_or(rest.len());
        let (run, tail) = rest.split_at(end);
        parts.push(if digit {
            (0, run.parse().unwrap_or(u64::MAX), String::new())
        } else {
            (1, 0, run.to_uppercase())
        });
        rest = tail;
    }
    parts
}

/// Reads a string or number as text. Null and empty strings count as missing.
fn text(v: &Value) -> Option<String> {
    match v {
        Value::String(s) if !s.is_empty() => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Settings;
    use crate::upstream::TjClient;
    use crate::upstream::fake::{Fake, count, fake, start};
    use axum::{body::Body, http::Request};
    use tower::ServiceExt;

    /// The example from Google's polyline docs, an empty input and a truncated one.
    #[test]
    fn decode_polyline_examples() {
        assert_eq!(
            decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@"),
            [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]]
        );
        assert!(decode_polyline("").is_empty());
        assert_eq!(decode_polyline("_p~iF~ps|U_ulL"), [[38.5, -120.2]]);
    }

    /// Null directions are skipped, stops without coordinates are dropped, and a
    /// direction without a polyline falls back to lines between its stops.
    #[test]
    fn normalize_route_shape() {
        let data = json!({
            "route": {"route_short_name": "1", "route_long_name": "Blok M - Kota", "route_desc": "BRT",
                      "route_color": "D62126", "route_text_color": "FFFFFF"},
            "outbound": {"trip_id": "1-R07", "headsign": "Kota", "polyline": "_p~iF~ps|U_ulLnnqC",
                         "stops": [{"stop_id": "S1", "stop_name": "Blok M", "stop_lat": -6.24, "stop_lon": 106.8,
                                    "bus_stop_type": "halte"}]},
            "inbound": {"trip_id": "1-R08", "headsign": "Blok M", "polyline": "",
                        "stops": [{"stop_id": "S2", "stop_lat": -6.13, "stop_lon": 106.81},
                                  {"stop_id": "S3", "stop_lat": -6.24, "stop_lon": 106.80},
                                  {"stop_id": "S4", "stop_lat": null, "stop_lon": 106.80}]},
            "loop": null,
        });
        let r = normalize_route("1", &data);
        assert_eq!(r["route_code"], "1");
        assert_eq!(r["route_name"], "Blok M - Kota");
        assert_eq!(r["route_type"], "BRT");
        let dirs = r["directions"].as_array().unwrap();
        assert_eq!(dirs.len(), 2);
        assert_eq!(dirs[0]["direction"], "outbound");
        assert_eq!(dirs[0]["path"], json!([[38.5, -120.2], [40.7, -120.95]]));
        assert_eq!(
            dirs[0]["stops"][0],
            json!({"stop_id": "S1", "name": "Blok M", "lat": -6.24, "lon": 106.8, "type": "halte"})
        );
        assert_eq!(dirs[1]["path"], json!([[-6.13, 106.81], [-6.24, 106.80]]));
        assert_eq!(dirs[1]["stops"].as_array().unwrap().len(), 2);
        assert_eq!(normalize_route("X", &Value::Null)["route_code"], "X");
    }

    /// Digit runs sort as numbers, before letters.
    #[test]
    fn natural_order() {
        let mut codes = ["10", "JAK.10", "1A", "2", "4D", "1", "JAK.2"];
        codes.sort_by_key(|c| natural_key(c));
        assert_eq!(codes, ["1", "1A", "2", "4D", "10", "JAK.2", "JAK.10"]);
    }

    /// A route the fake upstream knows, with one straight direction.
    fn detail(code: &str) -> Value {
        json!({"route": {"route_short_name": code, "route_color": "D62126"},
               "outbound": {"trip_id": format!("{code}-R1"), "headsign": "X", "polyline": "_p~iF~ps|U_ulLnnqC"}})
    }

    /// Builds the app against a fake upstream with BRT routes 10 and 1, Mikrotrans
    /// JAK.10 and a Rusun route. BRT 9 is listed but has no detail.
    async fn app_with_routes() -> (axum::Router, Fake) {
        let f = fake();
        {
            let mut s = f.lock().unwrap();
            s.routes = vec![
                json!({"route_short_name": "10", "route_desc": "BRT"}),
                json!({"route_short_name": "1", "route_desc": "brt "}),
                json!({"route_short_name": "9", "route_desc": "BRT"}),
                json!({"route_id": "JAK.10", "route_desc": "Mikrotrans"}),
                json!({"route_short_name": "R1", "route_desc": "Rusun"}),
            ];
            for code in ["10", "1", "JAK.10", "R1"] {
                s.route_details.insert(code.into(), detail(code));
            }
        }
        let client = TjClient::new(Settings::new(start(&f).await)).unwrap();
        (crate::app(AppState::new(client)), f)
    }

    /// Sends GET to the path and returns the status and the JSON body.
    async fn get(app: &axum::Router, path: &str) -> (u16, Value) {
        let res = app
            .clone()
            .oneshot(Request::get(path).body(Body::empty()).unwrap())
            .await
            .unwrap();
        let status = res.status().as_u16();
        let body = axum::body::to_bytes(res.into_body(), usize::MAX)
            .await
            .unwrap();
        (status, serde_json::from_slice(&body).unwrap())
    }

    /// Lists the route codes in a /routes response.
    fn codes(body: &Value) -> Vec<&str> {
        body["routes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| r["route_code"].as_str().unwrap())
            .collect()
    }

    /// /route-types counts the routes of each type, ignoring case and spaces.
    #[tokio::test]
    async fn route_types_counts() {
        let (app, _) = app_with_routes().await;
        let (status, body) = get(&app, "/route-types").await;
        assert_eq!(status, 200);
        let types = body["types"].as_array().unwrap();
        assert_eq!(types.len(), ROUTE_TYPES.len());
        assert_eq!(types[0], json!({"type": "BRT", "routes": 3}));
        assert_eq!(types[2], json!({"type": "Mikrotrans", "routes": 1}));
        assert_eq!(types[3], json!({"type": "Transjabodetabek", "routes": 0}));
    }

    /// Several types at once, in any case. Missing routes are skipped and the
    /// result is in natural order. The second call comes from the cache.
    #[tokio::test]
    async fn routes_of_several_types() {
        let (app, f) = app_with_routes().await;
        let (status, body) = get(&app, "/routes?type=brt,%20MIKROTRANS").await;
        assert_eq!(status, 200);
        assert_eq!(body["types"], json!(["BRT", "Mikrotrans"]));
        assert_eq!(codes(&body), ["1", "10", "JAK.10"]);
        assert_eq!(body["routes"][0]["directions"][0]["trip_id"], "1-R1");

        let upstream_calls = f.lock().unwrap().calls.len();
        let (_, again) = get(&app, "/routes?type=BRT,Mikrotrans").await;
        assert_eq!(again, body);
        assert_eq!(f.lock().unwrap().calls.len(), upstream_calls);
        assert_eq!(count(&f, "/v2/route/9"), 1);
    }

    /// No type means every route.
    #[tokio::test]
    async fn routes_without_type() {
        let (app, _) = app_with_routes().await;
        let (_, body) = get(&app, "/routes").await;
        assert_eq!(body["types"], json!([]));
        assert_eq!(codes(&body), ["1", "10", "JAK.10", "R1"]);
    }

    /// One unknown type rejects the whole request.
    #[tokio::test]
    async fn routes_unknown_type() {
        let (app, _) = app_with_routes().await;
        let (status, body) = get(&app, "/routes?type=BRT,xyz").await;
        assert_eq!(status, 400);
        assert!(body["detail"].as_str().unwrap().contains("xyz"));
    }

    /// A failing route list is a 502 that names the upstream path, not the host.
    #[tokio::test]
    async fn routes_upstream_error() {
        let f = fake();
        f.lock().unwrap().fail_logins = 99;
        let client = TjClient::new(Settings::new(start(&f).await)).unwrap();
        let app = crate::app(AppState::new(client));
        let (status, body) = get(&app, "/route-types").await;
        assert_eq!(status, 502);
        let detail = body["detail"].as_str().unwrap();
        assert!(detail.starts_with("upstream error: POST /v1/auth/login/guest"));
        assert!(!detail.contains("127.0.0.1"));
    }
}
