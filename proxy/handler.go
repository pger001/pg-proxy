package proxy

import (
	"bytes"
	"encoding/binary"
	"io"
	"log"
	"net"
	"time"

	"github.com/pger001/pg-proxy/stats"
)

// pgBackendMsgType constants for backend (server → client) messages we need
// to inspect for latency tracking.
const (
	msgReadyForQuery byte = 'Z' // sent after every complete query cycle
	msgErrorResponse byte = 'E' // query produced an error
)

// pendingQuery holds the SQL text and the wall-clock time at which it was
// dispatched to the backend, so that when ReadyForQuery arrives we can record
// an accurate round-trip latency.
type pendingQuery struct {
	query string
	start time.Time
}

// HandleConn proxies a single client connection to the PostgreSQL backend while
// collecting resource-consumption statistics.
//
// clientConn – the accepted TCP connection from the client.
// backendAddr – address of the real PostgreSQL server (e.g. "127.0.0.1:5433").
// col         – the statistics Collector to record metrics into.
func HandleConn(clientConn net.Conn, backendAddr string, col *stats.Collector) {
	defer clientConn.Close()
	col.ConnOpened()
	defer col.ConnClosed()

	backendConn, err := net.DialTimeout("tcp", backendAddr, 10*time.Second)
	if err != nil {
		log.Printf("[proxy] dial backend %s: %v", backendAddr, err)
		return
	}
	defer backendConn.Close()

	// pending is a buffered channel that carries SQL queries dispatched from
	// the client side so that the backend side can record accurate latencies
	// once ReadyForQuery arrives.
	pending := make(chan pendingQuery, 64)

	done := make(chan struct{}, 2)

	// client → backend (with query interception)
	go func() {
		defer func() {
			close(pending)
			done <- struct{}{}
		}()
		forwardClientToBackend(clientConn, backendConn, col, pending)
	}()

	// backend → client (with ReadyForQuery latency recording)
	go func() {
		defer func() { done <- struct{}{} }()
		forwardBackendToClient(backendConn, clientConn, col, pending)
	}()

	<-done
	// Close both connections to unblock the other goroutine.
	_ = clientConn.Close()
	_ = backendConn.Close()
	<-done
}

// forwardClientToBackend reads messages from the client, forwards them to the
// backend, and pushes pending query records for messages that carry SQL.
func forwardClientToBackend(client, backend net.Conn, col *stats.Collector, pending chan<- pendingQuery) {
	buf := make([]byte, 32*1024)

	// The PostgreSQL startup message does NOT have a message-type byte prefix;
	// it begins directly with a 4-byte length. Forward it transparently.
	startupHandled := false

	for {
		if !startupHandled {
			lenBuf := make([]byte, 4)
			if _, err := io.ReadFull(client, lenBuf); err != nil {
				return
			}
			msgLen := int(binary.BigEndian.Uint32(lenBuf))
			remaining := msgLen - 4
			body := make([]byte, remaining)
			if remaining > 0 {
				if _, err := io.ReadFull(client, body); err != nil {
					return
				}
			}
			full := append(lenBuf, body...)
			n, err := backend.Write(full)
			col.AddBytesFromClient(int64(n))
			if err != nil {
				return
			}
			startupHandled = true
			continue
		}

		// Read the 1-byte message type.
		if _, err := io.ReadFull(client, buf[:1]); err != nil {
			return
		}
		msgType := buf[0]

		// Read the 4-byte length.
		if _, err := io.ReadFull(client, buf[1:5]); err != nil {
			return
		}
		msgLen := int(binary.BigEndian.Uint32(buf[1:5]))
		payloadLen := msgLen - 4
		var payload []byte
		if payloadLen > 0 {
			payload = make([]byte, payloadLen)
			if _, err := io.ReadFull(client, payload); err != nil {
				return
			}
		}

		// Forward the message verbatim to the backend.
		full := make([]byte, 5+len(payload))
		full[0] = msgType
		copy(full[1:5], buf[1:5])
		copy(full[5:], payload)

		n, err := backend.Write(full)
		col.AddBytesFromClient(int64(n))
		if err != nil {
			return
		}

		// Enqueue pending queries so the backend side can record accurate
		// round-trip latencies once ReadyForQuery arrives.
		switch msgType {
		case msgQuery:
			if q := ExtractSimpleQuery(payload); q != "" {
				pending <- pendingQuery{query: normalizeQuery(q), start: time.Now()}
			}
		case msgParse:
			if q := ExtractParseName(payload); q != "" {
				pending <- pendingQuery{query: normalizeQuery(q), start: time.Now()}
			}
		case msgTerminate:
			return
		}
	}
}

// forwardBackendToClient copies backend messages to the client, counting bytes
// and finalising latency measurements when ReadyForQuery ('Z') is received.
func forwardBackendToClient(backend, client net.Conn, col *stats.Collector, pending <-chan pendingQuery) {
	buf := make([]byte, 32*1024)
	hasError := false

	for {
		// Read message type.
		if _, err := io.ReadFull(backend, buf[:1]); err != nil {
			return
		}
		msgType := buf[0]

		// Read the 4-byte length.
		if _, err := io.ReadFull(backend, buf[1:5]); err != nil {
			return
		}
		msgLen := int(binary.BigEndian.Uint32(buf[1:5]))
		payloadLen := msgLen - 4
		var payload []byte
		if payloadLen > 0 {
			payload = make([]byte, payloadLen)
			if _, err := io.ReadFull(backend, payload); err != nil {
				return
			}
		}

		// Forward to client.
		full := make([]byte, 5+len(payload))
		full[0] = msgType
		copy(full[1:5], buf[1:5])
		copy(full[5:], payload)

		n, err := client.Write(full)
		col.AddBytesToClient(int64(n))
		if err != nil {
			return
		}

		switch msgType {
		case msgErrorResponse:
			hasError = true
		case msgReadyForQuery:
			// Dequeue and finalise the matching pending query (if any).
			select {
			case pq, ok := <-pending:
				if ok {
					col.RecordQuery(pq.query, time.Since(pq.start), hasError)
				}
			default:
			}
			hasError = false
		}
	}
}

// normalizeQuery trims leading/trailing whitespace and collapses runs of
// whitespace to a single space to improve query grouping.
func normalizeQuery(q string) string {
	return string(bytes.Join(bytes.Fields([]byte(q)), []byte(" ")))
}
