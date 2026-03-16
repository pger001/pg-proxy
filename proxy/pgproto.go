// Package proxy implements the PostgreSQL TCP proxy with resource-tracking.
package proxy

import (
	"encoding/binary"
	"io"
)

// pgMsgType constants for the PostgreSQL frontend (client → server) messages
// we need to intercept.
const (
	msgQuery     byte = 'Q' // Simple Query
	msgParse     byte = 'P' // Extended Query – Parse
	msgTerminate byte = 'X' // Terminate
)

// ReadMessage reads a single PostgreSQL frontend wire-protocol message from r.
// It returns the message type byte and the payload (not including the 4-byte
// length prefix itself). If the reader returns io.EOF on the first byte the
// function returns ("", nil, io.EOF) so callers can distinguish a clean
// connection close from a mid-message EOF.
//
// Only the 5-byte+payload format is handled here (regular frontend messages).
// The Startup / SSL-request messages have a different layout but are forwarded
// transparently by the proxy without being parsed.
func ReadMessage(r io.Reader) (msgType byte, payload []byte, err error) {
	header := make([]byte, 5)
	if _, err = io.ReadFull(r, header); err != nil {
		return 0, nil, err
	}
	msgType = header[0]
	length := binary.BigEndian.Uint32(header[1:5])
	if length < 4 {
		// malformed; length includes its own 4 bytes
		return msgType, nil, nil
	}
	payloadLen := int(length) - 4
	if payloadLen == 0 {
		return msgType, nil, nil
	}
	payload = make([]byte, payloadLen)
	_, err = io.ReadFull(r, payload)
	return msgType, payload, err
}

// ExtractSimpleQuery parses a Simple Query ('Q') payload and returns the query
// string. The payload is a null-terminated string per the PostgreSQL protocol.
func ExtractSimpleQuery(payload []byte) string {
	if len(payload) == 0 {
		return ""
	}
	// strip trailing null bytes
	end := len(payload)
	for end > 0 && payload[end-1] == 0 {
		end--
	}
	return string(payload[:end])
}

// ExtractParseName parses an Extended Query Parse ('P') payload and returns
// the query string (second null-terminated string in the payload, after the
// statement name).
func ExtractParseName(payload []byte) string {
	if len(payload) == 0 {
		return ""
	}
	// First field: statement name (null-terminated); skip it.
	i := 0
	for i < len(payload) && payload[i] != 0 {
		i++
	}
	i++ // skip the null byte
	if i >= len(payload) {
		return ""
	}
	// Second field: query string (null-terminated)
	start := i
	for i < len(payload) && payload[i] != 0 {
		i++
	}
	return string(payload[start:i])
}
