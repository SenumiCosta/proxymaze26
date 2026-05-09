const axios = require('axios');
const https = require('https');
const http = require('http');
const state = require('../store/state');
const DEFAULTS = require('../config/defaults');

const TRANSIENT_CODES = new Set([500, 502, 503, 504]);
const MAX_DELIVERY_TIME_MS = 58000;
const PER_ATTEMPT_TIMEOUT_MS = 10000;
const RETRY_DELAYS_MS = DEFAULTS.webhook_retry_intervals_ms;

const httpsAgent = new https.Agent({ rejectUnauthorized: false, keepAlive: true });
const httpAgent = new http.Agent({ keepAlive: true });

class WebhookDelivery {
  constructor() {
    this.queues = new Map();
    this.successfulDeliveries = new Set();
  }

  deliverAll(payload) {
    const urls = [...new Set(state.webhooks.map(wh => wh.url))];
    for (const url of urls) {
      this.enqueue(url, payload);
    }
  }

  enqueue(url, payload) {
    const deliveryKey = this.deliveryKey(url, payload);
    if (this.successfulDeliveries.has(deliveryKey)) return;

    const prev = this.queues.get(url) || Promise.resolve();
    const next = prev
      .then(() => this.deliverWithRetry(url, payload, deliveryKey))
      .catch(err => console.error('[Webhook] Delivery error:', url, err && err.message));
    this.queues.set(url, next);
  }

  async deliverWithRetry(url, payload, deliveryKey) {
    if (this.successfulDeliveries.has(deliveryKey)) return;

    const deadline = Date.now() + MAX_DELIVERY_TIME_MS;
    let attempt = 0;
    let currentUrl = url;
    let redirectCount = 0;

    while (Date.now() < deadline) {
      const remaining = deadline - Date.now();
      const attemptTimeout = Math.min(PER_ATTEMPT_TIMEOUT_MS, remaining);
      if (attemptTimeout <= 100) return;

      const controller = new AbortController();
      const hardTimer = setTimeout(() => controller.abort(), attemptTimeout);

      try {
        const res = await axios.post(currentUrl, payload, {
          headers: { 'Content-Type': 'application/json' },
          proxy: false,
          httpAgent,
          httpsAgent,
          timeout: attemptTimeout,
          signal: controller.signal,
          validateStatus: () => true,
          maxRedirects: 0
        });

        if (res.status >= 200 && res.status < 300) {
          this.successfulDeliveries.add(deliveryKey);
          state.metrics.webhook_deliveries += 1;
          return;
        }

        if (res.status >= 300 && res.status < 400 && res.headers.location && redirectCount < 5) {
          currentUrl = new URL(res.headers.location, currentUrl).toString();
          redirectCount++;
          continue;
        }

        if (TRANSIENT_CODES.has(res.status)) {
          console.warn('[Webhook] transient', res.status, 'from', url, '- retrying');
          const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
          await this.wait(delay);
          attempt++;
          continue;
        }

        console.warn('[Webhook] non-transient', res.status, 'from', url, '- giving up');
        return;
      } catch (err) {
        console.warn('[Webhook] network error to', url, '-', err && err.message, '- retrying');
        const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
        await this.wait(delay);
        attempt++;
      } finally {
        clearTimeout(hardTimer);
      }
    }
    console.error('[Webhook] exhausted budget for', url);
  }

  wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  deliveryKey(url, payload) {
    return `${url}|${payload.event || 'event'}|${payload.alert_id || ''}`;
  }
}

module.exports = new WebhookDelivery();
