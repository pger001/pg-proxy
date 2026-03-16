// Package stats tracks runtime statistics about proxied PostgreSQL connections
// and queries.
package stats

import (
	"sync"
	"sync/atomic"
	"time"
)

// QueryStat records aggregated statistics for a single query text.
type QueryStat struct {
	Query      string        `json:"query"`
	ExecCount  int64         `json:"exec_count"`
	TotalTime  time.Duration `json:"total_time_ns"`
	MinTime    time.Duration `json:"min_time_ns"`
	MaxTime    time.Duration `json:"max_time_ns"`
	ErrorCount int64         `json:"error_count"`
}

// avgTime returns the average execution time; returns 0 when no executions.
func (q *QueryStat) avgTime() time.Duration {
	if q.ExecCount == 0 {
		return 0
	}
	return time.Duration(int64(q.TotalTime) / q.ExecCount)
}

// QueryStatView is the JSON-serialisable snapshot of a QueryStat.
type QueryStatView struct {
	Query      string `json:"query"`
	ExecCount  int64  `json:"exec_count"`
	TotalMS    int64  `json:"total_time_ms"`
	AvgMS      int64  `json:"avg_time_ms"`
	MinMS      int64  `json:"min_time_ms"`
	MaxMS      int64  `json:"max_time_ms"`
	ErrorCount int64  `json:"error_count"`
}

// Collector is the central statistics store.
// All methods are safe for concurrent use.
type Collector struct {
	mu sync.RWMutex

	// connection counters
	totalConns  int64 // total connections accepted (atomic)
	activeConns int64 // currently active connections (atomic)

	// byte counters (atomic)
	bytesFromClient int64
	bytesToClient   int64

	// per-query stats (protected by mu)
	queries map[string]*QueryStat

	startTime time.Time
}

// New creates and returns a ready-to-use Collector.
func New() *Collector {
	return &Collector{
		queries:   make(map[string]*QueryStat),
		startTime: time.Now(),
	}
}

// ConnOpened records that a new client connection has been established.
func (c *Collector) ConnOpened() {
	atomic.AddInt64(&c.totalConns, 1)
	atomic.AddInt64(&c.activeConns, 1)
}

// ConnClosed records that a client connection has been closed.
func (c *Collector) ConnClosed() {
	atomic.AddInt64(&c.activeConns, -1)
}

// AddBytesFromClient records bytes received from the client side.
func (c *Collector) AddBytesFromClient(n int64) {
	atomic.AddInt64(&c.bytesFromClient, n)
}

// AddBytesToClient records bytes sent to the client side.
func (c *Collector) AddBytesToClient(n int64) {
	atomic.AddInt64(&c.bytesToClient, n)
}

// RecordQuery records the outcome of a single query execution.
func (c *Collector) RecordQuery(query string, duration time.Duration, hasError bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	qs, ok := c.queries[query]
	if !ok {
		qs = &QueryStat{
			Query:   query,
			MinTime: duration,
			MaxTime: duration,
		}
		c.queries[query] = qs
	}

	qs.ExecCount++
	qs.TotalTime += duration
	if duration < qs.MinTime {
		qs.MinTime = duration
	}
	if duration > qs.MaxTime {
		qs.MaxTime = duration
	}
	if hasError {
		qs.ErrorCount++
	}
}

// Snapshot returns an immutable copy of the current statistics.
type Snapshot struct {
	UptimeSeconds   float64         `json:"uptime_seconds"`
	TotalConns      int64           `json:"total_connections"`
	ActiveConns     int64           `json:"active_connections"`
	BytesFromClient int64           `json:"bytes_from_client"`
	BytesToClient   int64           `json:"bytes_to_client"`
	Queries         []QueryStatView `json:"queries"`
}

// Snapshot collects and returns a point-in-time view of all statistics.
func (c *Collector) Snapshot() Snapshot {
	c.mu.RLock()
	queryViews := make([]QueryStatView, 0, len(c.queries))
	for _, qs := range c.queries {
		queryViews = append(queryViews, QueryStatView{
			Query:      qs.Query,
			ExecCount:  qs.ExecCount,
			TotalMS:    qs.TotalTime.Milliseconds(),
			AvgMS:      qs.avgTime().Milliseconds(),
			MinMS:      qs.MinTime.Milliseconds(),
			MaxMS:      qs.MaxTime.Milliseconds(),
			ErrorCount: qs.ErrorCount,
		})
	}
	c.mu.RUnlock()

	return Snapshot{
		UptimeSeconds:   time.Since(c.startTime).Seconds(),
		TotalConns:      atomic.LoadInt64(&c.totalConns),
		ActiveConns:     atomic.LoadInt64(&c.activeConns),
		BytesFromClient: atomic.LoadInt64(&c.bytesFromClient),
		BytesToClient:   atomic.LoadInt64(&c.bytesToClient),
		Queries:         queryViews,
	}
}

// Reset clears all collected statistics.
func (c *Collector) Reset() {
	c.mu.Lock()
	c.queries = make(map[string]*QueryStat)
	c.startTime = time.Now()
	c.mu.Unlock()

	atomic.StoreInt64(&c.totalConns, 0)
	atomic.StoreInt64(&c.activeConns, 0)
	atomic.StoreInt64(&c.bytesFromClient, 0)
	atomic.StoreInt64(&c.bytesToClient, 0)
}
