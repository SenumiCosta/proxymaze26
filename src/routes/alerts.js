const express = require('express');
const router = express.Router();
const state = require('../store/state');

// GET /alerts
router.get('/', (req, res) => {
  res.status(200).json(state.alerts);
});

module.exports = router;
