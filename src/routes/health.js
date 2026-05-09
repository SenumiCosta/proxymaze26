const express = require('express');
const router = express.Router();

// GET /health
router.get('/', (req, res) => {
  res.json({ status: 'ok' });
});

// GET /health/version - deploy marker.
const VERSION_TAG = 'v3-strict-iso-10s-timeout-' + new Date().toISOString();
router.get('/version', (req, res) => {
  res.json({ version: VERSION_TAG });
});

module.exports = router;
