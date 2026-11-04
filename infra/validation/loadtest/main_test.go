package main

import (
	"testing"
	"time"
)

func TestMeasurementIncludesFullWindowAndTailDrain(t *testing.T) {
	start := time.Now()
	if got := measurementElapsed(10, start, start.Add(9*time.Second)); got != 10 {
		t.Fatalf("short drain: %v", got)
	}
	if got := measurementElapsed(10, start, start.Add(12*time.Second)); got != 12 {
		t.Fatalf("tail drain: %v", got)
	}
}
