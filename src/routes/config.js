const express = require('express');
const router = express.Router();
const state = require('../store/state');
const monitor = require('../services/monitor');

router.post('/', (req, res) => {
  const { check_interval_seconds, request_timeout_ms } = req.body;
  if (check_interval_seconds !== undefined) {
    const interval = Number.parseInt(check_interval_seconds, 10);
    if (!Number.isFinite(interval) || interval <= 0) {
      return res.status(400).json({ error: 'check_interval_seconds must be a positive integer' });
    }
    state.config.check_interval_seconds = interval;
  }
  if (request_timeout_ms !== undefined) {
    const timeout = Number.parseInt(request_timeout_ms, 10);
    if (!Number.isFinite(timeout) || timeout <= 0) {
      return res.status(400).json({ error: 'request_timeout_ms must be a positive integer' });
    }
    state.config.request_timeout_ms = timeout;
  }
  monitor.restart();
  monitor.triggerImmediate();
  res.status(200).json(state.config);
});

router.get('/', (req, res) => {
  res.status(200).json(state.config);
});

module.exports = router;
