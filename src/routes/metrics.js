const express = require('express');
const router = express.Router();
const state = require('../store/state');

// GET /metrics
router.get('/', (req, res) => {
  res.status(200).json({
    total_checks: state.metrics.total_checks,
    current_pool_size: state.proxies.size,
    active_alerts: state.activeAlert ? 1 : 0,
    total_alerts: state.alerts.length,
    webhook_deliveries: state.metrics.webhook_deliveries
  });
});

module.exports = router;
