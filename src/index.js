const app = require('./app');
const DEFAULTS = require('./config/defaults');
const monitor = require('./services/monitor');

const PORT = process.env.PORT || DEFAULTS.server_port;

app.listen(PORT, () => {
  console.log(`[ProxyMaze] Watchtower active on port ${PORT}`);
  console.log(`[ProxyMaze] Initializing background monitor...`);
  monitor.start();
});
