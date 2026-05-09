const express = require('express');
const router = express.Router();
const state = require('../store/state');
const crypto = require('crypto');

// POST /webhooks
router.post('/', (req, res) => {
  const { url } = req.body;
  if (typeof url !== 'string' || url.length === 0) {
    return res.status(400).json({ error: 'url is required' });
  }

  const existing = state.webhooks.find(webhook => webhook.url === url);
  if (existing) {
    return res.status(201).json(existing);
  }

  const webhook_id = 'wh-' + crypto.randomUUID().slice(0, 8);
  const webhook = { webhook_id, url };
  state.webhooks.push(webhook);
  res.status(201).json(webhook);
});

module.exports = router;
