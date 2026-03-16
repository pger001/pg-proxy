package stats

import (
	"testing"
	"time"
)

func TestConnCounters(t *testing.T) {
	c := New()

	c.ConnOpened()
	c.ConnOpened()
	snap := c.Snapshot()
	if snap.TotalConns != 2 {
		t.Errorf("TotalConns: want 2, got %d", snap.TotalConns)
	}
	if snap.ActiveConns != 2 {
		t.Errorf("ActiveConns: want 2, got %d", snap.ActiveConns)
	}

	c.ConnClosed()
	snap = c.Snapshot()
	if snap.ActiveConns != 1 {
		t.Errorf("ActiveConns after close: want 1, got %d", snap.ActiveConns)
	}
	// total should not decrease
	if snap.TotalConns != 2 {
		t.Errorf("TotalConns after close: want 2, got %d", snap.TotalConns)
	}
}

func TestByteCounters(t *testing.T) {
	c := New()
	c.AddBytesFromClient(100)
	c.AddBytesToClient(200)
	snap := c.Snapshot()
	if snap.BytesFromClient != 100 {
		t.Errorf("BytesFromClient: want 100, got %d", snap.BytesFromClient)
	}
	if snap.BytesToClient != 200 {
		t.Errorf("BytesToClient: want 200, got %d", snap.BytesToClient)
	}
}

func TestRecordQuery(t *testing.T) {
	c := New()

	q := "SELECT 1"
	c.RecordQuery(q, 10*time.Millisecond, false)
	c.RecordQuery(q, 20*time.Millisecond, false)
	c.RecordQuery(q, 5*time.Millisecond, true)

	snap := c.Snapshot()
	if len(snap.Queries) != 1 {
		t.Fatalf("want 1 query stat, got %d", len(snap.Queries))
	}
	qs := snap.Queries[0]
	if qs.ExecCount != 3 {
		t.Errorf("ExecCount: want 3, got %d", qs.ExecCount)
	}
	if qs.ErrorCount != 1 {
		t.Errorf("ErrorCount: want 1, got %d", qs.ErrorCount)
	}
	if qs.MinMS != 5 {
		t.Errorf("MinMS: want 5, got %d", qs.MinMS)
	}
	if qs.MaxMS != 20 {
		t.Errorf("MaxMS: want 20, got %d", qs.MaxMS)
	}
	wantTotal := int64((10 + 20 + 5))
	if qs.TotalMS != wantTotal {
		t.Errorf("TotalMS: want %d, got %d", wantTotal, qs.TotalMS)
	}
	wantAvg := int64(35 / 3) // integer ms
	if qs.AvgMS != wantAvg {
		t.Errorf("AvgMS: want %d, got %d", wantAvg, qs.AvgMS)
	}
}

func TestReset(t *testing.T) {
	c := New()
	c.ConnOpened()
	c.AddBytesFromClient(99)
	c.RecordQuery("SELECT 2", time.Millisecond, false)

	c.Reset()
	snap := c.Snapshot()
	if snap.TotalConns != 0 {
		t.Errorf("after Reset TotalConns: want 0, got %d", snap.TotalConns)
	}
	if snap.BytesFromClient != 0 {
		t.Errorf("after Reset BytesFromClient: want 0, got %d", snap.BytesFromClient)
	}
	if len(snap.Queries) != 0 {
		t.Errorf("after Reset Queries: want 0, got %d", len(snap.Queries))
	}
}
