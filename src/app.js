const express = require('express');

const healthRoutes = require('./routes/health');
const configRoutes = require('./routes/config');
const proxiesRoutes = require('./routes/proxies');
const alertsRoutes = require('./routes/alerts');
const webhooksRoutes = require('./routes/webhooks');
const integrationsRoutes = require('./routes/integrations');
const metricsRoutes = require('./routes/metrics');

const app = express();

app.use(express.json());

app.get('/', (req, res) => {
  res.status(200).json({ message: "ProxyMaze'26 API is running!" });
});

app.use('/health', healthRoutes);
app.use('/config', configRoutes);
app.use('/proxies', proxiesRoutes);
app.use('/alerts', alertsRoutes);
app.use('/webhooks', webhooksRoutes);
app.use('/integrations', integrationsRoutes);
app.use('/metrics', metricsRoutes);

app.use((err, req, res, next) => {
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    return res.status(400).json({ error: 'Malformed JSON' });
  }
  return next(err);
});

module.exports = app;
