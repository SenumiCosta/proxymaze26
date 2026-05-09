const express = require('express');
const router = express.Router();
const state = require('../store/state');

// POST /integrations
router.post('/', (req, res) => {
  const { type, webhook_url, username, events } = req.body;
  if (!['slack', 'discord'].includes(type) || typeof webhook_url !== 'string' || webhook_url.length === 0) {
    return res.status(400).json({ error: 'valid type and webhook_url are required' });
  }

  const evts = Array.isArray(events) && events.length > 0
    ? events
    : ['alert.fired', 'alert.resolved'];

  const existing = state.integrations.find(item => item.type === type && item.webhook_url === webhook_url);
  if (existing) {
    existing.username = username || existing.username;
    existing.events = [...new Set([...(existing.events || []), ...evts])];
    return res.status(201).json(existing);
  }

  state.integrations.push({ type, webhook_url, username, events: evts });
  res.status(201).json({ type, webhook_url, username, events: evts });
});

module.exports = router;
