package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func request(t *testing.T, client *http.Client, method, url string, body []byte, key string) *http.Response {
	t.Helper()
	req, err := http.NewRequest(method, url, bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if len(body) > 0 {
		req.Header.Set("Content-Type", "application/json")
	}
	if key != "" {
		req.Header.Set("X-Api-Key", key)
	}
	response, err := client.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return response
}

func TestMonitoringHTTPFlow(t *testing.T) {
	state := filepath.Join(t.TempDir(), "state.json")
	t.Setenv("HC_DATA_FILE", state)
	app := NewApp()
	server := httptest.NewServer(app)
	defer server.Close()

	response := request(t, server.Client(), http.MethodPost, server.URL+"/__test/reset/", nil, "")
	if response.StatusCode != http.StatusOK {
		t.Fatalf("reset: got %d", response.StatusCode)
	}
	response.Body.Close()

	payload := []byte(`{"name":"nightly-backup","slug":"nightly-backup","timeout":60,"grace":60,"subject":"completed","filter_body":true,"filter_http_body":true}`)
	response = request(t, server.Client(), http.MethodPost, server.URL+"/api/v3/checks/", payload, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
	if response.StatusCode != http.StatusCreated {
		t.Fatalf("create: got %d", response.StatusCode)
	}
	var created map[string]any
	if err := json.NewDecoder(response.Body).Decode(&created); err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	code, ok := created["uuid"].(string)
	if !ok || !isValidUUID(code) {
		t.Fatalf("unexpected UUID: %#v", created["uuid"])
	}

	response = request(t, server.Client(), http.MethodPost, server.URL+"/ping/"+code, []byte("completed"), "")
	if response.StatusCode != http.StatusOK || response.Header.Get("Ping-Body-Limit") != "10000" {
		t.Fatalf("ping: got %d, limit %q", response.StatusCode, response.Header.Get("Ping-Body-Limit"))
	}
	response.Body.Close()

	response = request(t, server.Client(), http.MethodGet, server.URL+"/api/v3/checks/"+code, nil, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
	if response.StatusCode != http.StatusOK {
		t.Fatalf("read: got %d", response.StatusCode)
	}
	var fetched map[string]any
	if err := json.NewDecoder(response.Body).Decode(&fetched); err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if fetched["status"] != "up" || fetched["n_pings"].(float64) != 1 || fetched["subject"] != "completed" || fetched["filter_body"] != true {
		t.Fatalf("unexpected check state: %#v", fetched)
	}

	response = request(t, server.Client(), http.MethodPost, server.URL+"/api/v3/checks/"+code+"/pause", nil, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
	if response.StatusCode != http.StatusOK {
		t.Fatalf("pause: got %d", response.StatusCode)
	}
	response.Body.Close()

	if _, err := os.Stat(state); err != nil {
		t.Fatalf("state was not persisted: %v", err)
	}

	reloaded := NewApp()
	reloaded.store.mu.RLock()
	stored := reloaded.store.checks[code]
	reloaded.store.mu.RUnlock()
	if stored == nil || stored.Status != "paused" || stored.NPings != 1 {
		t.Fatalf("unexpected persisted state: %#v", stored)
	}
}

func TestManagementValidation(t *testing.T) {
	t.Setenv("HC_DATA_FILE", filepath.Join(t.TempDir(), "state.json"))
	server := httptest.NewServer(NewApp())
	defer server.Close()

	for _, payload := range [][]byte{
		[]byte(`{"schedule":"* * * * *","tz":"not-a-timezone"}`),
		[]byte(`{"name":"backup","unique":["status"]}`),
	} {
		response := request(t, server.Client(), http.MethodPost, server.URL+"/api/v3/checks/", payload, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
		if response.StatusCode != http.StatusBadRequest {
			response.Body.Close()
			t.Fatalf("invalid request: got %d", response.StatusCode)
		}
		response.Body.Close()
	}

	response := request(t, server.Client(), http.MethodPost, server.URL+"/api/v3/checks/", []byte(`{"name":"backup"}`), "RRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRR")
	if response.StatusCode != http.StatusUnauthorized {
		response.Body.Close()
		t.Fatalf("read-only key: got %d", response.StatusCode)
	}
	response.Body.Close()
}

func TestScheduledCheckTiming(t *testing.T) {
	lastPing := time.Date(2026, time.January, 2, 3, 1, 10, 0, time.UTC)
	cron := &Check{Kind: "cron", Schedule: "*/5 * * * *", Timezone: "UTC", LastPing: &lastPing, Grace: time.Minute, Status: "up"}
	if next := (&Store{}).nextPing(cron); next == nil || !next.Equal(time.Date(2026, time.January, 2, 3, 5, 0, 0, time.UTC)) {
		t.Fatalf("unexpected cron next ping: %v", next)
	}

	lastPing = time.Date(2026, time.January, 2, 12, 35, 0, 0, time.UTC)
	calendar := &Check{Kind: "oncalendar", Schedule: "12:34", Timezone: "UTC", LastPing: &lastPing, Grace: time.Minute, Status: "up"}
	if next := (&Store{}).nextPing(calendar); next == nil || !next.Equal(time.Date(2026, time.January, 3, 12, 34, 0, 0, time.UTC)) {
		t.Fatalf("unexpected calendar next ping: %v", next)
	}

	if validSchedule("bad schedule") || validSchedule("* * * * * *") || !validSchedule("*/5 * * * *") {
		t.Fatal("schedule validation did not distinguish valid cron expressions")
	}
}
