# pg-proxy

A lightweight PostgreSQL **resource-consumption statistics proxy** written in Go.

pg-proxy sits transparently between your application and PostgreSQL, tracking:

| Metric | Description |
|---|---|
| `total_connections` | Total client connections accepted since startup (or last reset) |
| `active_connections` | Connections currently open |
| `bytes_from_client` | Total bytes received from all clients |
| `bytes_to_client` | Total bytes sent back to all clients |
| `queries[].exec_count` | Number of times each query was executed |
| `queries[].avg_time_ms` | Average execution latency (ms) |
| `queries[].min_time_ms` / `max_time_ms` | Min / max latency (ms) |
| `queries[].total_time_ms` | Cumulative execution time (ms) |
| `queries[].error_count` | Number of executions that returned an error |

---

## Quick Start

```bash
# 1. Build
go build -o pg-proxy .

# 2. Run (defaults: listens on :5432, forwards to :5433, metrics on :9090)
./pg-proxy

# 3. Or use a config file
./pg-proxy -config config.example.json
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `PG_PROXY_LISTEN` | `0.0.0.0:5432` | Address the proxy listens on |
| `PG_PROXY_BACKEND` | `127.0.0.1:5433` | Upstream PostgreSQL address |
| `PG_PROXY_METRICS_LISTEN` | `0.0.0.0:9090` | HTTP metrics server address |

### JSON config file

```json
{
  "listen":          "0.0.0.0:5432",
  "backend":         "127.0.0.1:5433",
  "metrics_listen":  "0.0.0.0:9090"
}
```

---

## Metrics HTTP API

| Endpoint | Method | Description |
|---|---|---|
| `GET /metrics` | GET | JSON snapshot of all statistics |
| `POST /metrics/reset` | POST | Reset all statistics to zero |
| `GET /health` | GET | Liveness check (returns `{"status":"healthy"}`) |

**Example:**

```bash
curl http://localhost:9090/metrics | jq .
```

```json
{
  "uptime_seconds": 42.3,
  "total_connections": 17,
  "active_connections": 3,
  "bytes_from_client": 20480,
  "bytes_to_client": 102400,
  "queries": [
    {
      "query": "SELECT * FROM users WHERE id = $1",
      "exec_count": 120,
      "total_time_ms": 360,
      "avg_time_ms": 3,
      "min_time_ms": 1,
      "max_time_ms": 25,
      "error_count": 0
    }
  ]
}
```

---

## Architecture

```
Client app
    │  (PostgreSQL wire protocol)
    ▼
┌──────────────────────┐
│      pg-proxy        │   :5432
│  ┌────────────────┐  │
│  │  proxy.Handler │  │──────────────────► PostgreSQL  :5433
│  └───────┬────────┘  │  (transparent TCP forward)
│          │ records   │
│  ┌───────▼────────┐  │
│  │ stats.Collector│  │
│  └───────┬────────┘  │
│          │           │
│  ┌───────▼────────┐  │
│  │ metrics.Server │  │──────► GET /metrics  :9090
│  └────────────────┘  │
└──────────────────────┘
```

## Development

```bash
go test ./...   # run all tests
go vet ./...    # static analysis
go build ./...  # build all packages
```
