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

class IntegrationDelivery {
  constructor() {
    this.queues = new Map();
    this.successfulDeliveries = new Set();
  }

  deliverAll(alert, eventType) {
    const seenTargets = new Set();
    const targets = [...state.integrations];
    for (const integration of targets) {
      if (!integration.events || !integration.events.includes(eventType)) continue;
      const targetKey = `${integration.type}|${integration.webhook_url}`;
      if (seenTargets.has(targetKey)) continue;
      seenTargets.add(targetKey);

      const payload = this.buildPayload(integration.type, alert, eventType, integration);
      if (payload) {
        this.enqueue(integration.webhook_url, payload, eventType, alert.alert_id, integration.type);
      }
    }
  }

  buildPayload(type, alert, eventType, integration) {
    if (type === 'slack') return this.buildSlackPayload(alert, eventType, integration);
    if (type === 'discord') return this.buildDiscordPayload(alert, eventType, integration);
    return null;
  }

  enqueue(url, payload, eventType, alertId, integrationType) {
    const deliveryKey = `${integrationType}|${url}|${eventType}|${alertId}`;
    if (this.successfulDeliveries.has(deliveryKey)) return;

    const prev = this.queues.get(url) || Promise.resolve();
    const next = prev
      .then(() => this.deliverWithRetry(url, payload, deliveryKey))
      .catch(err => console.error('[Integration] Delivery failed:', url, err.message));
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
          console.warn('[Integration] transient', res.status, 'from', url, '- retrying');
          const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
          await this.wait(delay);
          attempt++;
          continue;
        }

        console.warn('[Integration] non-transient', res.status, 'from', url, '- giving up');
        return;
      } catch (err) {
        console.warn('[Integration] network error to', url, '-', err && err.message);
        const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
        await this.wait(delay);
        attempt++;
      } finally {
        clearTimeout(hardTimer);
      }
    }
    console.error('[Integration] exhausted budget for', url);
  }

  wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  buildSlackPayload(alert, event, integration) {
    const isResolved = event === 'alert.resolved';
    const title = isResolved ? 'Alert Resolved' : 'Alert Fired';
    const text = isResolved
      ? `Alert ${alert.alert_id} resolved`
      : 'Proxy pool failure rate exceeded threshold';
    const fields = [
      { title: 'Alert ID', value: String(alert.alert_id) },
      { title: 'Failure Rate', value: String(alert.failure_rate) },
      { title: 'Failed Proxies', value: String(alert.failed_proxies) },
      { title: 'Threshold', value: String(alert.threshold) },
      { title: 'Failed IDs', value: (alert.failed_proxy_ids || []).join(', ') || 'none' },
      { title: 'Fired At', value: String(alert.fired_at) }
    ];
    if (isResolved) {
      fields.push({ title: 'Resolved At', value: String(alert.resolved_at) });
    }

    return {
      username: integration.username || 'ProxyWatch',
      text,
      blocks: [
        {
          type: 'header',
          text: {
            type: 'plain_text',
            text: title
          }
        },
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text
          }
        },
        {
          type: 'section',
          fields: fields.map(field => ({
            type: 'mrkdwn',
            text: `*${field.title}:*\n${field.value}`
          }))
        }
      ],
      attachments: [{
        color: isResolved ? '#36a64f' : '#FF0000',
        fields,
        footer: 'ProxyMaze Alert System',
        ts: Math.floor(Date.now() / 1000)
      }]
    };
  }

  buildDiscordPayload(alert, event, integration) {
    const isResolved = event === 'alert.resolved';
    const fields = [
      { name: 'Alert ID', value: String(alert.alert_id) },
      { name: 'Failure Rate', value: String(alert.failure_rate) },
      { name: 'Failed Proxies', value: String(alert.failed_proxies) },
      { name: 'Threshold', value: String(alert.threshold) },
      { name: 'Failed IDs', value: (alert.failed_proxy_ids || []).join(', ') || 'none' }
    ];
    if (isResolved) {
      fields.push({ name: 'Resolved At', value: String(alert.resolved_at) });
    }

    return {
      embeds: [{
        title: isResolved ? 'Alert Resolved' : 'Alert Fired',
        description: isResolved
          ? `Alert ${alert.alert_id} has been resolved`
          : 'Proxy pool failure rate exceeded threshold',
        color: isResolved ? 3066993 : 16711680,
        fields,
        footer: { text: 'ProxyMaze Alert System' },
        timestamp: new Date().toISOString()
      }]
    };
  }
}

module.exports = new IntegrationDelivery();
