const axios = require('axios');
const https = require('https');
const http = require('http');
const state = require('../store/state');

const httpsAgent = new https.Agent({ rejectUnauthorized: false, keepAlive: false });
const httpAgent = new http.Agent({ keepAlive: false });
const MAX_CONCURRENCY = 50;

class ProbeRunner {
  async probeAll(proxies) {
    const workers = Array.from(
      { length: Math.min(MAX_CONCURRENCY, proxies.length) },
      async (_, workerIndex) => {
        for (let i = workerIndex; i < proxies.length; i += MAX_CONCURRENCY) {
          await this.probeOne(proxies[i]);
        }
      }
    );
    await Promise.allSettled(workers);
  }

  async probeOne(proxy) {
    const timeout = state.config.request_timeout_ms;
    const checkedAt = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    let newStatus = 'down';

    const controller = new AbortController();
    const hardTimer = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await axios.get(proxy.url, {
        timeout,
        httpAgent,
        httpsAgent,
        proxy: false,
        validateStatus: () => true,
        maxRedirects: 5,
        signal: controller.signal
      });
      newStatus = (response.status >= 200 && response.status < 300) ? 'up' : 'down';
    } catch {
      newStatus = 'down';
    } finally {
      clearTimeout(hardTimer);
    }

    proxy.status = newStatus;
    proxy.last_checked_at = checkedAt;
    proxy.consecutive_failures = newStatus === 'down' ? proxy.consecutive_failures + 1 : 0;
    proxy.history.push({ checked_at: checkedAt, status: newStatus });
    proxy.total_checks += 1;
    state.metrics.total_checks += 1;
  }
}

module.exports = new ProbeRunner();
