package proxy

import (
	"encoding/binary"
	"net"
	"testing"
	"time"

	"github.com/pger001/pg-proxy/stats"
)

// buildClientMsg constructs a typed frontend message: 1-byte type + 4-byte
// length + payload.
func buildClientMsg(t byte, payload []byte) []byte {
	msg := make([]byte, 5+len(payload))
	msg[0] = t
	binary.BigEndian.PutUint32(msg[1:5], uint32(4+len(payload)))
	copy(msg[5:], payload)
	return msg
}

// buildBackendMsg constructs a typed backend message (same layout as frontend).
func buildBackendMsg(t byte, payload []byte) []byte {
	return buildClientMsg(t, payload)
}

// fakePostgres listens on ln and acts as a minimal PostgreSQL backend:
//   - drains the startup message
//   - for each Simple Query ('Q') it receives, responds with ReadyForQuery ('Z')
//   - stops after stopAfter queries
func fakePostgres(t *testing.T, ln net.Listener, stopAfter int) {
	t.Helper()
	conn, err := ln.Accept()
	if err != nil {
		return
	}
	defer conn.Close()

	// drain startup (4-byte length-prefixed)
	lenBuf := make([]byte, 4)
	if _, err := readFull(conn, lenBuf); err != nil {
		return
	}
	msgLen := int(binary.BigEndian.Uint32(lenBuf))
	body := make([]byte, msgLen-4)
	readFull(conn, body) //nolint:errcheck

	for i := 0; i < stopAfter; i++ {
		hdr := make([]byte, 5)
		if _, err := readFull(conn, hdr); err != nil {
			return
		}
		msgLen := int(binary.BigEndian.Uint32(hdr[1:5]))
		payload := make([]byte, msgLen-4)
		readFull(conn, payload) //nolint:errcheck

		// Send ReadyForQuery response
		rfq := buildBackendMsg(msgReadyForQuery, []byte{'I'}) // 'I' = idle
		conn.Write(rfq)                                       //nolint:errcheck
	}
}

// readFull is a local wrapper to keep tests self-contained.
func readFull(conn net.Conn, buf []byte) (int, error) {
	total := 0
	for total < len(buf) {
		n, err := conn.Read(buf[total:])
		total += n
		if err != nil {
			return total, err
		}
	}
	return total, nil
}

// buildStartupMsg builds a minimal PostgreSQL startup message.
func buildStartupMsg() []byte {
	// protocol version 3.0 = 0x0003_0000
	body := []byte{0x00, 0x03, 0x00, 0x00}
	msgLen := 4 + len(body)
	msg := make([]byte, 4+len(body))
	binary.BigEndian.PutUint32(msg[:4], uint32(msgLen))
	copy(msg[4:], body)
	return msg
}

func TestHandleConn_queryLatencyRecorded(t *testing.T) {
	// Start fake backend listener.
	backendLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer backendLn.Close()

	col := stats.New()

	// Start fake backend: handle 1 query then stop.
	go fakePostgres(t, backendLn, 1)

	// Start proxy listener.
	proxyLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer proxyLn.Close()

	go func() {
		conn, err := proxyLn.Accept()
		if err != nil {
			return
		}
		HandleConn(conn, backendLn.Addr().String(), col)
	}()

	// Connect as a fake client.
	clientConn, err := net.DialTimeout("tcp", proxyLn.Addr().String(), 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer clientConn.Close()

	// Send startup message.
	startup := buildStartupMsg()
	if _, err := clientConn.Write(startup); err != nil {
		t.Fatal(err)
	}

	// Send a Simple Query.
	query := "SELECT 1"
	qPayload := append([]byte(query), 0)
	qMsg := buildClientMsg(msgQuery, qPayload)
	if _, err := clientConn.Write(qMsg); err != nil {
		t.Fatal(err)
	}

	// Wait for ReadyForQuery to arrive at the client.
	rfqBuf := make([]byte, 6) // 1 type + 4 len + 1 payload
	readFull(clientConn, rfqBuf)

	// Give the proxy goroutine a moment to record stats.
	time.Sleep(50 * time.Millisecond)

	snap := col.Snapshot()
	if len(snap.Queries) != 1 {
		t.Fatalf("expected 1 query stat, got %d", len(snap.Queries))
	}
	qs := snap.Queries[0]
	if qs.Query != "SELECT 1" {
		t.Errorf("query text: got %q, want %q", qs.Query, "SELECT 1")
	}
	if qs.ExecCount != 1 {
		t.Errorf("ExecCount: got %d, want 1", qs.ExecCount)
	}
	if qs.ErrorCount != 0 {
		t.Errorf("ErrorCount: got %d, want 0", qs.ErrorCount)
	}
	if col.Snapshot().BytesFromClient == 0 {
		t.Error("BytesFromClient should be > 0")
	}
}
