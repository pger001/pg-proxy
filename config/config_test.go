package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestDefault(t *testing.T) {
	cfg := Default()
	if cfg.Listen == "" {
		t.Error("Listen should not be empty")
	}
	if cfg.Backend == "" {
		t.Error("Backend should not be empty")
	}
}

func TestLoad(t *testing.T) {
	want := &Config{
		Listen:        "0.0.0.0:6432",
		Backend:       "10.0.0.1:5432",
		MetricsListen: "0.0.0.0:8080",
	}

	f, err := os.CreateTemp(t.TempDir(), "pg-proxy-cfg-*.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := json.NewEncoder(f).Encode(want); err != nil {
		t.Fatal(err)
	}
	f.Close()

	got, err := Load(f.Name())
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got.Listen != want.Listen {
		t.Errorf("Listen: want %q, got %q", want.Listen, got.Listen)
	}
	if got.Backend != want.Backend {
		t.Errorf("Backend: want %q, got %q", want.Backend, got.Backend)
	}
	if got.MetricsListen != want.MetricsListen {
		t.Errorf("MetricsListen: want %q, got %q", want.MetricsListen, got.MetricsListen)
	}
}

func TestLoad_notFound(t *testing.T) {
	_, err := Load(filepath.Join(t.TempDir(), "nonexistent.json"))
	if err == nil {
		t.Error("expected error for missing file")
	}
}

func TestLoadFromEnv(t *testing.T) {
	t.Setenv("PG_PROXY_LISTEN", "0.0.0.0:7777")
	t.Setenv("PG_PROXY_BACKEND", "db.example.com:5432")
	t.Setenv("PG_PROXY_METRICS_LISTEN", "")

	cfg := Default()
	cfg.LoadFromEnv()

	if cfg.Listen != "0.0.0.0:7777" {
		t.Errorf("Listen: want 0.0.0.0:7777, got %s", cfg.Listen)
	}
	if cfg.Backend != "db.example.com:5432" {
		t.Errorf("Backend: want db.example.com:5432, got %s", cfg.Backend)
	}
}
