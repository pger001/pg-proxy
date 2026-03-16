// Package config provides configuration management for pg-proxy.
package config

import (
	"encoding/json"
	"fmt"
	"os"
)

// Config holds the full application configuration.
type Config struct {
	// Listen is the address the proxy listens on (e.g. "0.0.0.0:5432").
	Listen string `json:"listen"`

	// Backend is the upstream PostgreSQL server address (e.g. "127.0.0.1:5433").
	Backend string `json:"backend"`

	// MetricsListen is the address the HTTP metrics server listens on
	// (e.g. "0.0.0.0:9090"). Leave empty to disable the metrics server.
	MetricsListen string `json:"metrics_listen"`
}

// Default returns a Config populated with sensible defaults.
func Default() *Config {
	return &Config{
		Listen:        "0.0.0.0:5432",
		Backend:       "127.0.0.1:5433",
		MetricsListen: "0.0.0.0:9090",
	}
}

// Load reads a JSON config file and returns the parsed Config.
// Missing fields fall back to Default values.
func Load(path string) (*Config, error) {
	cfg := Default()

	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open config file: %w", err)
	}
	defer f.Close()

	if err := json.NewDecoder(f).Decode(cfg); err != nil {
		return nil, fmt.Errorf("parse config file: %w", err)
	}
	return cfg, nil
}

// LoadFromEnv overrides config fields from environment variables.
//
//	PG_PROXY_LISTEN          – overrides Listen
//	PG_PROXY_BACKEND         – overrides Backend
//	PG_PROXY_METRICS_LISTEN  – overrides MetricsListen
func (c *Config) LoadFromEnv() {
	if v := os.Getenv("PG_PROXY_LISTEN"); v != "" {
		c.Listen = v
	}
	if v := os.Getenv("PG_PROXY_BACKEND"); v != "" {
		c.Backend = v
	}
	if v := os.Getenv("PG_PROXY_METRICS_LISTEN"); v != "" {
		c.MetricsListen = v
	}
}
