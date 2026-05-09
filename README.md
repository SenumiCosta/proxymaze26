# ProxyMaze'26

Real-Time Proxy Intelligence Challenge - Torch Labs Sri Lanka

## Quick Start

```bash
npm install
npm run dev
npm start
```

## Render

Use the Node runtime with:

```bash
npm install
npm start
```

If an existing Render service was previously configured for Python, update its build
command to `npm install` and its start command to `npm start`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |
| POST | `/config` | Set monitoring configuration |
| GET | `/config` | Get current configuration |
| POST | `/proxies` | Load proxy URLs into pool |
| GET | `/proxies` | Pool summary + per-proxy state |
| GET | `/proxies/:id` | Single proxy details |
| GET | `/proxies/:id/history` | Proxy check history |
| DELETE | `/proxies` | Clear proxy pool |
| GET | `/alerts` | All alerts, active and resolved |
| POST | `/webhooks` | Register webhook receiver |
| POST | `/integrations` | Register Slack/Discord integration |
| GET | `/metrics` | Operational metrics |

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3000` | HTTP server port |
