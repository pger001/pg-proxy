package proxy

import (
	"testing"
)

func TestNormalizeQuery(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"SELECT 1", "SELECT 1"},
		{"  SELECT   1  ", "SELECT 1"},
		{"SELECT\n1", "SELECT 1"},
		{"", ""},
	}
	for _, tt := range tests {
		got := normalizeQuery(tt.input)
		if got != tt.want {
			t.Errorf("normalizeQuery(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}
