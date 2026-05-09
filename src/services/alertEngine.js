const crypto = require('crypto');
const state = require('../store/state');
const webhookDelivery = require('./webhookDelivery');
const integrationDelivery = require('./integrationDelivery');

const THRESHOLD = 0.2;

// Spec example timestamps use second precision (no milliseconds): "2026-04-24T10:15:30Z"
function isoSeconds(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

class AlertEngine {
  evaluate() {
    const proxies = Array.from(state.proxies.values());
    const total = proxies.length;

    const downProxies = proxies.filter(p => p.status === 'down');
    const down = downProxies.length;
    const failureRate = total === 0 ? 0 : down / total;
    const failedIds = downProxies.map(p => p.id).sort();

    if (total === 0) {
      if (state.activeAlert) this.resolveAlert();
      return;
    }

    if (!state.activeAlert && failureRate >= THRESHOLD) {
      this.fireAlert(total, down, failureRate, failedIds);
    } else if (state.activeAlert && failureRate >= THRESHOLD) {
      this.updateActiveAlert(total, down, failureRate, failedIds);
    } else if (state.activeAlert && failureRate < THRESHOLD) {
      this.resolveAlert();
    }
  }

  fireAlert(total, down, failureRate, failedIds) {
    const alertId = 'alert-' + crypto.randomUUID().slice(0, 8);
    const firedAt = isoSeconds();

    const alert = {
      alert_id: alertId,
      status: 'active',
      failure_rate: failureRate,
      total_proxies: total,
      failed_proxies: down,
      failed_proxy_ids: [...failedIds],
      threshold: THRESHOLD,
      fired_at: firedAt,
      resolved_at: null,
      message: 'Proxy pool failure rate exceeded threshold'
    };

    state.activeAlert = alert;
    state.alerts.push(alert);

    webhookDelivery.deliverAll({
      event: 'alert.fired',
      alert_id: alertId,
      fired_at: firedAt,
      failure_rate: failureRate,
      total_proxies: total,
      failed_proxies: down,
      failed_proxy_ids: [...failedIds],
      threshold: THRESHOLD,
      message: alert.message
    });

    integrationDelivery.deliverAll(alert, 'alert.fired');
  }

  updateActiveAlert(total, down, failureRate, failedIds) {
    const alert = state.activeAlert;
    alert.total_proxies = total;
    alert.failed_proxy_ids = [...failedIds];
    alert.failed_proxies = down;
    alert.failure_rate = failureRate;
  }

  resolveAlert() {
    const alert = state.activeAlert;
    const resolvedAt = isoSeconds();

    alert.status = 'resolved';
    alert.resolved_at = resolvedAt;
    state.activeAlert = null;

    webhookDelivery.deliverAll({
      event: 'alert.resolved',
      alert_id: alert.alert_id,
      resolved_at: resolvedAt
    });

    integrationDelivery.deliverAll(alert, 'alert.resolved');
  }
}

module.exports = new AlertEngine();
