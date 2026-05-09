const DEFAULTS = require('../config/defaults');

const initialState = {
  config: { 
    check_interval_seconds: DEFAULTS.check_interval_seconds, 
    request_timeout_ms: DEFAULTS.request_timeout_ms 
  },
  
  // Map<string, ProxyObject>
  // id → { id, url, status, last_checked_at, consecutive_failures, history[], total_checks }
  proxies: new Map(),
  
  // Array of Alert objects (Active + Resolved)
  alerts: [],
  
  // Reference to current active alert (or null)
  activeAlert: null,
  
  // Array of { webhook_id, url }
  webhooks: [],
  
  // Array of { type, webhook_url, username, events }
  integrations: [],
  
  metrics: { 
    total_checks: 0, 
    webhook_deliveries: 0 
  }
};

if (!globalThis.__proxyMazeState) {
  globalThis.__proxyMazeState = initialState;
}

module.exports = globalThis.__proxyMazeState;
