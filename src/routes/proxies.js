const express = require('express');
const router = express.Router();
const state = require('../store/state');
const monitor = require('../services/monitor');

function extractProxyId(urlStr) {
  try {
    const parsed = new URL(urlStr);
    const segments = parsed.pathname.split('/').filter(Boolean);
    if (segments.length > 0) return segments[segments.length - 1];
    return parsed.hostname || urlStr;
  } catch {
    const parts = urlStr.split('/').filter(Boolean);
    return parts[parts.length - 1] || urlStr || 'unknown';
  }
}

router.post('/', (req, res) => {
  const { replace = false } = req.body;
  const proxies = Array.isArray(req.body.proxies) ? req.body.proxies : [];

  if (replace) {
    state.proxies.clear();
  }

  const accepted = [];
  for (const url of proxies) {
    if (typeof url !== 'string' || url.trim().length === 0) continue;
    const cleanUrl = url.trim();
    const id = extractProxyId(cleanUrl);
    state.proxies.set(id, {
      id,
      url: cleanUrl,
      status: 'pending',
      last_checked_at: null,
      consecutive_failures: 0,
      history: [],
      total_checks: 0
    });
    accepted.push({ id, url: cleanUrl, status: 'pending' });
  }

  if (accepted.length > 0 || replace) {
    monitor.triggerImmediate();
  }

  res.status(201).json({ accepted: accepted.length, proxies: accepted });
});

function proxySummary(proxy) {
  const upChecks = proxy.history.filter(h => h.status === 'up').length;
  const uptime_percentage = proxy.total_checks === 0
    ? 0
    : Number(((upChecks / proxy.total_checks) * 100).toFixed(1));

  return {
    id: proxy.id,
    url: proxy.url,
    status: proxy.status,
    last_checked_at: proxy.last_checked_at,
    consecutive_failures: proxy.consecutive_failures,
    total_checks: proxy.total_checks,
    uptime_percentage,
    history: proxy.history
  };
}

router.get('/', (req, res) => {
  const all = Array.from(state.proxies.values());
  const total = all.length;
  const up = all.filter(p => p.status === 'up').length;
  const down = all.filter(p => p.status === 'down').length;
  const failure_rate = total === 0 ? 0 : down / total;

  res.status(200).json({
    total,
    up,
    down,
    failure_rate,
    proxies: all.map(proxySummary)
  });
});

router.get('/:id', (req, res) => {
  const proxy = state.proxies.get(req.params.id);
  if (!proxy) return res.status(404).json({ error: 'Proxy not found' });

  res.status(200).json(proxySummary(proxy));
});

router.get('/:id/history', (req, res) => {
  const proxy = state.proxies.get(req.params.id);
  if (!proxy) return res.status(404).json({ error: 'Proxy not found' });
  res.status(200).json(proxy.history);
});

router.delete('/', (req, res) => {
  state.proxies.clear();
  monitor.triggerImmediate();
  res.status(204).send();
});

module.exports = router;
