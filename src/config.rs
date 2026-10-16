//! Settings read from TJ_ environment variables.

use std::collections::hash_map::RandomState;
use std::hash::BuildHasher;
use std::time::Duration;

/// Runtime settings. The defaults match the headers the Android app sends.
pub struct Settings {
    pub base_url: String,
    pub timeout: Duration,
    /// How often the bus feed polls the upstream while a client is listening.
    pub poll: Duration,
    pub app_version: String,
    pub app_os: String,
    pub app_os_version: String,
    pub app_platform: String,
    pub device_model: String,
    pub device_id: String,
    pub lang: String,
    pub fcm_token: String,
}

impl Settings {
    /// Builds settings with default values, pointed at the given upstream base URL.
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            timeout: Duration::from_secs(15),
            poll: Duration::from_millis(333),
            app_version: "3.0.4".into(),
            app_os: "android".into(),
            app_os_version: "14".into(),
            app_platform: "34".into(),
            device_model: "Google|Pixel 8".into(),
            // A fresh id per process unless TJ_DEVICE_ID pins one, same as the Python app.
            device_id: format!("{:016x}", RandomState::new().hash_one(0u8)),
            lang: "id".into(),
            fcm_token: String::new(),
        }
    }

    /// Reads settings from the environment. TJ_BASE_URL is required because the
    /// upstream host is kept out of the source tree.
    pub fn from_env() -> Result<Self, String> {
        let base_url = env("BASE_URL").ok_or("TJ_BASE_URL is not set, see .env.example")?;

        let mut s = Self::new(base_url);

        for (key, field) in [
            ("TIMEOUT_SECONDS", &mut s.timeout),
            ("POLL_SECONDS", &mut s.poll),
        ] {
            if let Some(v) = env(key) {
                *field = v
                    .parse()
                    .ok()
                    .and_then(|secs| Duration::try_from_secs_f64(secs).ok())
                    .filter(|d| !d.is_zero())
                    .ok_or(format!("TJ_{key} must be a positive number"))?;
            }
        }

        for (key, field) in [
            ("APP_VERSION", &mut s.app_version),
            ("APP_OS", &mut s.app_os),
            ("APP_OS_VERSION", &mut s.app_os_version),
            ("APP_PLATFORM", &mut s.app_platform),
            ("DEVICE_MODEL", &mut s.device_model),
            ("DEVICE_ID", &mut s.device_id),
            ("LANG", &mut s.lang),
            ("FCM_TOKEN", &mut s.fcm_token),
        ] {
            if let Some(v) = env(key) {
                *field = v;
            }
        }
        Ok(s)
    }
}

/// Returns the value of TJ_{key}, treating an empty value as unset.
fn env(key: &str) -> Option<String> {
    std::env::var(format!("TJ_{key}"))
        .ok()
        .filter(|v| !v.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Two processes get different device ids, and each id is 16 hex characters.
    #[test]
    fn device_id_is_random_hex() {
        let a = Settings::new("http://x").device_id;
        let b = Settings::new("http://x").device_id;
        assert_eq!(a.len(), 16);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    /// The default poll interval gives three polls per second.
    #[test]
    fn default_poll_is_three_per_second() {
        assert_eq!(Settings::new("http://x").poll, Duration::from_millis(333));
    }
}
