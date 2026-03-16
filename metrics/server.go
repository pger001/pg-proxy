// Package metrics exposes an HTTP server that serves live statistics.
package metrics

import (
	"encoding/json"
	"log"
	"net/http"

	"github.com/pger001/pg-proxy/stats"
)

// Server is a lightweight HTTP server that exposes collected statistics.
type Server struct {
	col  *stats.Collector
	mux  *http.ServeMux
	addr string
}

// New creates a new metrics Server bound to addr, using col for statistics.
func New(addr string, col *stats.Collector) *Server {
	s := &Server{
		col:  col,
		mux:  http.NewServeMux(),
		addr: addr,
	}
	s.mux.HandleFunc("/metrics", s.handleMetrics)
	s.mux.HandleFunc("/metrics/reset", s.handleReset)
	s.mux.HandleFunc("/health", s.handleHealth)
	return s
}

// ListenAndServe starts the HTTP server. It blocks until the server stops.
func (s *Server) ListenAndServe() error {
	srv := &http.Server{
		Addr:    s.addr,
		Handler: s.mux,
	}
	log.Printf("[metrics] listening on %s", s.addr)
	return srv.ListenAndServe()
}

// handleMetrics writes a JSON snapshot of current statistics.
func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	snap := s.col.Snapshot()
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(snap); err != nil {
		log.Printf("[metrics] encode snapshot: %v", err)
	}
}

// handleReset clears all collected statistics when called with POST.
func (s *Server) handleReset(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	s.col.Reset()
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

// handleHealth returns a simple 200 OK for liveness checks.
func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"healthy"}`))
}
