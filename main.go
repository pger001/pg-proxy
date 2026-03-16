// pg-proxy – a PostgreSQL resource-consumption statistics proxy.
//
// Usage:
//
//	pg-proxy [-config path/to/config.json]
//
// Environment variables (override JSON config):
//
//	PG_PROXY_LISTEN         proxy listen address        (default: 0.0.0.0:5432)
//	PG_PROXY_BACKEND        upstream PostgreSQL address (default: 127.0.0.1:5433)
//	PG_PROXY_METRICS_LISTEN HTTP metrics listen address (default: 0.0.0.0:9090)
package main

import (
	"flag"
	"log"
	"net"

	"github.com/pger001/pg-proxy/config"
	"github.com/pger001/pg-proxy/metrics"
	"github.com/pger001/pg-proxy/proxy"
	"github.com/pger001/pg-proxy/stats"
)

func main() {
	configPath := flag.String("config", "", "path to JSON config file (optional)")
	flag.Parse()

	var cfg *config.Config
	if *configPath != "" {
		var err error
		cfg, err = config.Load(*configPath)
		if err != nil {
			log.Fatalf("load config: %v", err)
		}
	} else {
		cfg = config.Default()
	}
	cfg.LoadFromEnv()

	col := stats.New()

	// Start the metrics HTTP server.
	if cfg.MetricsListen != "" {
		metricsSrv := metrics.New(cfg.MetricsListen, col)
		go func() {
			if err := metricsSrv.ListenAndServe(); err != nil {
				log.Fatalf("[metrics] server error: %v", err)
			}
		}()
	}

	// Start the proxy TCP listener.
	ln, err := net.Listen("tcp", cfg.Listen)
	if err != nil {
		log.Fatalf("[proxy] listen %s: %v", cfg.Listen, err)
	}
	log.Printf("[proxy] listening on %s → backend %s", cfg.Listen, cfg.Backend)

	for {
		conn, err := ln.Accept()
		if err != nil {
			log.Printf("[proxy] accept: %v", err)
			continue
		}
		go proxy.HandleConn(conn, cfg.Backend, col)
	}
}
