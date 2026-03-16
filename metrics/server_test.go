package metrics

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/pger001/pg-proxy/stats"
)

func newTestServer(t *testing.T) (*Server, *stats.Collector) {
	t.Helper()
	col := stats.New()
	srv := New(":0", col)
	return srv, col
}

func TestHandleMetrics_empty(t *testing.T) {
	srv, _ := newTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rr := httptest.NewRecorder()
	srv.handleMetrics(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", rr.Code)
	}
	var snap map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &snap); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, ok := snap["uptime_seconds"]; !ok {
		t.Error("missing uptime_seconds field")
	}
}

func TestHandleMetrics_withData(t *testing.T) {
	srv, col := newTestServer(t)
	col.ConnOpened()
	col.AddBytesFromClient(512)
	col.RecordQuery("SELECT 1", 5*time.Millisecond, false)

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rr := httptest.NewRecorder()
	srv.handleMetrics(rr, req)

	var snap stats.Snapshot
	if err := json.Unmarshal(rr.Body.Bytes(), &snap); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if snap.TotalConns != 1 {
		t.Errorf("TotalConns: want 1, got %d", snap.TotalConns)
	}
	if snap.BytesFromClient != 512 {
		t.Errorf("BytesFromClient: want 512, got %d", snap.BytesFromClient)
	}
	if len(snap.Queries) != 1 {
		t.Fatalf("Queries: want 1, got %d", len(snap.Queries))
	}
}

func TestHandleMetrics_methodNotAllowed(t *testing.T) {
	srv, _ := newTestServer(t)
	req := httptest.NewRequest(http.MethodPost, "/metrics", nil)
	rr := httptest.NewRecorder()
	srv.handleMetrics(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Errorf("want 405, got %d", rr.Code)
	}
}

func TestHandleReset(t *testing.T) {
	srv, col := newTestServer(t)
	col.ConnOpened()
	col.RecordQuery("SELECT 1", time.Millisecond, false)

	req := httptest.NewRequest(http.MethodPost, "/metrics/reset", nil)
	rr := httptest.NewRecorder()
	srv.handleReset(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "ok") {
		t.Error("expected ok in reset response")
	}

	// stats should now be zeroed
	snap := col.Snapshot()
	if snap.TotalConns != 0 {
		t.Errorf("after reset TotalConns: want 0, got %d", snap.TotalConns)
	}
}

func TestHandleHealth(t *testing.T) {
	srv, _ := newTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rr := httptest.NewRecorder()
	srv.handleHealth(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "healthy") {
		t.Errorf("want 'healthy' in body, got %s", rr.Body.String())
	}
}
