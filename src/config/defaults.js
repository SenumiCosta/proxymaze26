const DEFAULTS = {
  check_interval_seconds: 15,
  request_timeout_ms: 3000,
  alert_threshold: 0.20,
  webhook_retry_intervals_ms: [500, 1000, 2000, 4000, 8000, 8000],
  server_port: 3000
};

module.exports = DEFAULTS;
