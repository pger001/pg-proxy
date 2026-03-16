package proxy

import (
	"testing"
)

func TestExtractSimpleQuery(t *testing.T) {
	tests := []struct {
		name    string
		payload []byte
		want    string
	}{
		{"normal", append([]byte("SELECT 1"), 0), "SELECT 1"},
		{"no null", []byte("SELECT 2"), "SELECT 2"},
		{"empty", []byte{}, ""},
		{"only null", []byte{0}, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ExtractSimpleQuery(tt.payload)
			if got != tt.want {
				t.Errorf("got %q, want %q", got, tt.want)
			}
		})
	}
}

func TestExtractParseName(t *testing.T) {
	// payload: <stmt-name>\0<query>\0...
	build := func(stmt, query string) []byte {
		b := []byte(stmt)
		b = append(b, 0)
		b = append(b, []byte(query)...)
		b = append(b, 0)
		return b
	}
	tests := []struct {
		name    string
		payload []byte
		want    string
	}{
		{"named stmt", build("s1", "SELECT $1"), "SELECT $1"},
		{"unnamed stmt", build("", "INSERT INTO t VALUES($1)"), "INSERT INTO t VALUES($1)"},
		{"empty payload", []byte{}, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ExtractParseName(tt.payload)
			if got != tt.want {
				t.Errorf("got %q, want %q", got, tt.want)
			}
		})
	}
}
