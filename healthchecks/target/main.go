// Healthchecks is a small, dependency-free Go implementation of an uptime
// monitoring HTTP service. Scheduled jobs call a per-check ping URL. The
// service records the result and exposes an authenticated management API.
package main

import (
	"crypto/rand"
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	defaultTimeout = 24 * time.Hour
	defaultGrace   = time.Hour
	maxInterval    = 365 * 24 * time.Hour
)

var uuidPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type Project struct {
	ID          int
	Name        string
	PingKey     string
	APIKey      string
	ReadOnlyKey string
	BadgeKey    string
	CheckLimit  int
}

type Check struct {
	Code              string
	BadgeKey          string
	ProjectID         int
	Name              string
	Slug              string
	Tags              string
	Description       string
	Kind              string
	Timeout           time.Duration
	Grace             time.Duration
	Schedule          string
	Timezone          string
	Methods           string
	ManualResume      bool
	FilterSubject     bool
	FilterBody        bool
	FilterHTTPBody    bool
	FilterDefaultFail bool
	StartKeyword      string
	SuccessKeyword    string
	FailureKeyword    string
	Status            string
	Created           time.Time
	LastPing          *time.Time
	LastStart         *time.Time
	LastStartRID      string
	LastDuration      *time.Duration
	AlertAfter        *time.Time
	NPings            int
	Pings             []Ping
	Flips             []Flip
}

type Ping struct {
	N          int
	Created    time.Time
	Kind       string
	Scheme     string
	RemoteAddr string
	Method     string
	UserAgent  string
	Body       []byte
	ExitStatus *int
	RID        string
}

type Flip struct {
	Created   time.Time
	OldStatus string
	NewStatus string
	Reason    string
}

type Store struct {
	mu       sync.RWMutex
	projects map[int]*Project
	checks   map[string]*Check
	nextID   int
	dataPath string
}

type persistedState struct {
	Projects map[int]*Project  `json:"projects"`
	Checks   map[string]*Check `json:"checks"`
	NextID   int               `json:"next_id"`
}

func NewStore() *Store {
	dataPath := os.Getenv("HC_DATA_FILE")
	if dataPath == "" {
		dataPath = "healthchecks-data.json"
	}
	s := &Store{projects: make(map[int]*Project), checks: make(map[string]*Check), dataPath: dataPath}
	if !s.load() {
		s.reset()
		s.persist()
	}
	return s
}

func (s *Store) load() bool {
	data, err := os.ReadFile(s.dataPath)
	if err != nil {
		return false
	}
	state := persistedState{}
	if err := json.Unmarshal(data, &state); err != nil || len(state.Projects) == 0 {
		return false
	}
	s.projects, s.checks, s.nextID = state.Projects, state.Checks, state.NextID
	if s.checks == nil {
		s.checks = make(map[string]*Check)
	}
	return true
}

// persist writes a complete state snapshot using rename semantics so that a
// stopped process never leaves a half-written state file behind.
func (s *Store) persist() {
	state := persistedState{Projects: s.projects, Checks: s.checks, NextID: s.nextID}
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		log.Printf("cannot serialise state: %v", err)
		return
	}
	temporary := s.dataPath + ".tmp"
	if err := os.WriteFile(temporary, data, 0600); err != nil {
		log.Printf("cannot write state: %v", err)
		return
	}
	if err := os.Rename(temporary, s.dataPath); err != nil {
		// Windows does not permit Rename to replace an existing file, unlike
		// Linux. Retrying after removal keeps the program portable for local
		// development while Linux retains its atomic replacement path.
		if removeErr := os.Remove(s.dataPath); removeErr != nil {
			log.Printf("cannot save state: %v", err)
			return
		}
		if retryErr := os.Rename(temporary, s.dataPath); retryErr != nil {
			log.Printf("cannot save state: %v", retryErr)
		}
	}
}

func (s *Store) reset() {
	s.projects = make(map[int]*Project)
	s.checks = make(map[string]*Check)
	s.nextID = 2
	s.projects[1] = &Project{
		ID:          1,
		Name:        "Alices Project",
		PingKey:     strings.Repeat("p", 22),
		APIKey:      strings.Repeat("X", 32),
		ReadOnlyKey: strings.Repeat("R", 32),
		BadgeKey:    "alice",
		CheckLimit:  1000,
	}
}

func newUUID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(fmt.Sprintf("unable to obtain random bytes: %v", err))
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func checkUniqueKey(code string) string {
	compact := strings.ReplaceAll(code, "-", "")
	if len(compact) > 16 {
		compact = compact[:16]
	}
	sum := sha1.Sum([]byte(compact))
	return hex.EncodeToString(sum[:])
}

func iso(t *time.Time) any {
	if t == nil {
		return nil
	}
	return t.UTC().Format(time.RFC3339)
}

func durationSeconds(d time.Duration) int64 {
	return int64(d / time.Second)
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeText(w http.ResponseWriter, status int, body string) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(status)
	_, _ = io.WriteString(w, body)
}

func cors(w http.ResponseWriter, methods string) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Headers", "X-Api-Key")
	w.Header().Set("Access-Control-Allow-Methods", methods)
	w.Header().Set("Access-Control-Max-Age", "600")
}

func siteRoot(r *http.Request) string {
	scheme := r.Header.Get("X-Forwarded-Proto")
	if scheme == "" {
		scheme = "http"
	}
	host := r.Host
	if host == "" {
		host = "localhost:8000"
	}
	return scheme + "://" + host
}

func (s *Store) projectForKey(key string, readOnlyAllowed bool) (*Project, bool) {
	for _, project := range s.projects {
		if key == project.APIKey {
			return project, false
		}
		if readOnlyAllowed && key == project.ReadOnlyKey {
			return project, true
		}
	}
	return nil, false
}

func (s *Store) findCheckBySlug(pingKey, slug string) *Check {
	for _, check := range s.checks {
		project := s.projects[check.ProjectID]
		if project != nil && project.PingKey == pingKey && check.Slug == slug {
			return check
		}
	}
	return nil
}

func (s *Store) checksForProject(projectID int) []*Check {
	checks := make([]*Check, 0)
	for _, check := range s.checks {
		if check.ProjectID == projectID {
			checks = append(checks, check)
		}
	}
	sort.Slice(checks, func(i, j int) bool { return checks[i].Created.Before(checks[j].Created) })
	return checks
}

func (s *Store) currentStatus(check *Check, now time.Time) string {
	if check.Status == "paused" || check.Status == "new" || check.Status == "down" {
		return check.Status
	}
	if check.LastStart != nil && now.After(check.LastStart.Add(check.Grace)) {
		return "down"
	}
	if graceStart := s.nextPing(check); graceStart != nil {
		if now.After(graceStart.Add(check.Grace)) {
			return "down"
		}
		if now.After(*graceStart) {
			return "grace"
		}
	}
	return "up"
}

func (s *Store) nextPing(check *Check) *time.Time {
	if check.LastPing == nil {
		return nil
	}
	switch check.Kind {
	case "simple":
		next := check.LastPing.Add(check.Timeout)
		return &next
	case "cron":
		return nextCron(check.Schedule, check.Timezone, *check.LastPing)
	case "oncalendar":
		return nextOnCalendar(check.Schedule, check.Timezone, *check.LastPing)
	default:
		return nil
	}
}

// nextCron evaluates the standard five-field minute/hour/day/month/weekday
// format used by Healthchecks. It supports wildcards, lists, ranges, steps,
// and individual numeric values. The bounded minute scan keeps the behaviour
// deterministic without adding a third-party scheduler package.
func nextCron(schedule, timezone string, after time.Time) *time.Time {
	fields := strings.Fields(schedule)
	if len(fields) != 5 {
		return nil
	}
	location, err := time.LoadLocation(timezone)
	if err != nil {
		location = time.UTC
	}
	candidate := after.In(location).Truncate(time.Minute).Add(time.Minute)
	limit := candidate.AddDate(2, 0, 0)
	for candidate.Before(limit) {
		if cronFieldMatches(fields[0], candidate.Minute(), 0, 59) &&
			cronFieldMatches(fields[1], candidate.Hour(), 0, 23) &&
			cronFieldMatches(fields[2], candidate.Day(), 1, 31) &&
			cronFieldMatches(fields[3], int(candidate.Month()), 1, 12) &&
			cronFieldMatches(fields[4], int(candidate.Weekday()), 0, 6) {
			result := candidate.UTC()
			return &result
		}
		candidate = candidate.Add(time.Minute)
	}
	return nil
}

func cronFieldMatches(expression string, value, minimum, maximum int) bool {
	for _, item := range strings.Split(expression, ",") {
		step := 1
		base := item
		hasStep := strings.Contains(item, "/")
		if hasStep {
			parts := strings.Split(item, "/")
			if len(parts) != 2 {
				continue
			}
			parsed, err := strconv.Atoi(parts[1])
			if err != nil || parsed <= 0 {
				continue
			}
			step, base = parsed, parts[0]
		}
		start, end := minimum, maximum
		if base != "*" {
			if strings.Contains(base, "-") {
				parts := strings.Split(base, "-")
				if len(parts) != 2 {
					continue
				}
				var firstErr, secondErr error
				start, firstErr = strconv.Atoi(parts[0])
				end, secondErr = strconv.Atoi(parts[1])
				if firstErr != nil || secondErr != nil {
					continue
				}
			} else {
				parsed, err := strconv.Atoi(base)
				if err != nil {
					continue
				}
				start, end = parsed, parsed
				if hasStep {
					end = maximum
				}
			}
		}
		if start < minimum || end > maximum || start > end {
			continue
		}
		if value >= start && value <= end && (value-start)%step == 0 {
			return true
		}
	}
	return false
}

// nextOnCalendar covers the common daily HH:MM form. More elaborate natural
// language schedules are rejected at validation time until their full parser
// is ported, rather than being silently interpreted incorrectly.
func nextOnCalendar(schedule, timezone string, after time.Time) *time.Time {
	if !regexp.MustCompile(`^([01][0-9]|2[0-3]):[0-5][0-9]$`).MatchString(schedule) {
		return nil
	}
	location, err := time.LoadLocation(timezone)
	if err != nil {
		location = time.UTC
	}
	parts := strings.Split(schedule, ":")
	hour, _ := strconv.Atoi(parts[0])
	minute, _ := strconv.Atoi(parts[1])
	local := after.In(location)
	candidate := time.Date(local.Year(), local.Month(), local.Day(), hour, minute, 0, 0, location)
	if !candidate.After(local) {
		candidate = candidate.AddDate(0, 0, 1)
	}
	result := candidate.UTC()
	return &result
}

func (s *Store) toCheckJSON(check *Check, project *Project, version int, readonly bool, r *http.Request) map[string]any {
	status := s.currentStatus(check, time.Now())
	base := siteRoot(r)
	result := map[string]any{
		"name":                check.Name,
		"slug":                check.Slug,
		"tags":                check.Tags,
		"desc":                check.Description,
		"grace":               durationSeconds(check.Grace),
		"n_pings":             check.NPings,
		"status":              status,
		"started":             check.LastStart != nil,
		"last_ping":           iso(check.LastPing),
		"next_ping":           iso(s.nextPing(check)),
		"manual_resume":       check.ManualResume,
		"methods":             check.Methods,
		"subject":             conditionalString(check.FilterSubject, check.SuccessKeyword),
		"subject_fail":        conditionalString(check.FilterSubject, check.FailureKeyword),
		"start_kw":            check.StartKeyword,
		"success_kw":          check.SuccessKeyword,
		"failure_kw":          check.FailureKeyword,
		"filter_subject":      check.FilterSubject,
		"filter_body":         check.FilterBody,
		"filter_http_body":    check.FilterHTTPBody,
		"filter_default_fail": check.FilterDefaultFail,
		"badge_url":           fmt.Sprintf("%s/b/2/%s.svg", base, check.BadgeKey),
	}
	if check.LastDuration != nil {
		result["last_duration"] = durationSeconds(*check.LastDuration)
	}
	if check.Kind == "simple" {
		result["timeout"] = durationSeconds(check.Timeout)
	} else {
		result["schedule"] = check.Schedule
		result["tz"] = check.Timezone
	}
	if readonly {
		result["unique_key"] = checkUniqueKey(check.Code)
		return result
	}
	result["uuid"] = check.Code
	result["ping_url"] = base + "/ping/" + check.Code
	updateURL := fmt.Sprintf("%s/api/v%d/checks/%s", base, version, check.Code)
	result["update_url"] = updateURL
	result["pause_url"] = updateURL + "/pause"
	result["resume_url"] = updateURL + "/resume"
	result["channels"] = ""
	return result
}

func conditionalString(condition bool, value string) string {
	if condition {
		return value
	}
	return ""
}

type App struct {
	store         *Store
	pingBodyLimit int64
	metricsKey    string
}

func NewApp() *App {
	limit := int64(10000)
	if raw := os.Getenv("PING_BODY_LIMIT"); raw != "" {
		if value, err := strconv.ParseInt(raw, 10, 64); err == nil && value >= 0 {
			limit = value
		}
	}
	return &App{store: NewStore(), pingBodyLimit: limit, metricsKey: os.Getenv("METRICS_KEY")}
}

type dashboardCheck struct {
	Code     string
	Name     string
	Status   string
	Pings    int
	NextPing string
}

type dashboardData struct {
	Title  string
	Checks []dashboardCheck
}

var dashboardTemplate = template.Must(template.New("dashboard").Parse(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{.Title}}</title><style>
body{font-family:system-ui,sans-serif;margin:0;background:#f4f6f8;color:#18212b}header{padding:1.25rem 8%;background:#14324a;color:#fff}main{max-width:960px;margin:2rem auto;padding:0 1rem}.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px #0002;padding:1rem}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.75rem;border-bottom:1px solid #e5e7eb}.up{color:#137333}.down{color:#b3261e}.grace{color:#a15c00}.new,.paused{color:#5f6368}a{color:#145da0;text-decoration:none}.empty{padding:2rem;text-align:center;color:#5f6368}</style></head>
<body><header><strong>Healthchecks</strong><span style="margin-left:.5rem">Go monitoring service</span></header><main><div class="card"><h1>Your checks</h1>{{if .Checks}}<table><thead><tr><th>Check</th><th>Status</th><th>Pings</th><th>Next expected ping</th></tr></thead><tbody>{{range .Checks}}<tr><td><a href="/checks/{{.Code}}">{{.Name}}</a></td><td class="{{.Status}}">{{.Status}}</td><td>{{.Pings}}</td><td>{{.NextPing}}</td></tr>{{end}}</tbody></table>{{else}}<div class="empty">No checks have been created yet. Use the API to create one, then ping its private URL.</div>{{end}}</div></main></body></html>`))

var detailTemplate = template.Must(template.New("detail").Parse(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{.Name}} · Healthchecks</title><style>body{font-family:system-ui,sans-serif;margin:0;background:#f4f6f8;color:#18212b}header{padding:1.25rem 8%;background:#14324a;color:#fff}main{max-width:960px;margin:2rem auto;padding:0 1rem}.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px #0002;padding:1rem;margin-bottom:1rem}code{background:#edf2f7;padding:.2rem .35rem;border-radius:4px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.65rem;border-bottom:1px solid #e5e7eb}a{color:#145da0}.up{color:#137333}.down{color:#b3261e}</style></head>
<body><header><a style="color:#fff" href="/">Healthchecks</a></header><main><div class="card"><h1>{{.Name}}</h1><p>Status: <strong class="{{.Status}}">{{.Status}}</strong></p><p>Ping URL: <code>{{.PingURL}}</code></p><p>Received pings: {{.Pings}}</p></div><div class="card"><h2>Recent events</h2><table><thead><tr><th>When</th><th>Event</th><th>Source</th></tr></thead><tbody>{{range .Events}}<tr><td>{{.When}}</td><td>{{.Kind}}</td><td>{{.Source}}</td></tr>{{end}}</tbody></table></div></main></body></html>`))

func (a *App) handleDashboard(w http.ResponseWriter, r *http.Request) {
	a.store.mu.RLock()
	project := a.store.projects[1]
	checks := a.store.checksForProject(1)
	items := make([]dashboardCheck, 0, len(checks))
	for _, check := range checks {
		name := check.Name
		if name == "" {
			name = check.Code
		}
		next := "—"
		if when := a.store.nextPing(check); when != nil {
			next = when.Local().Format("2006-01-02 15:04:05")
		}
		items = append(items, dashboardCheck{Code: check.Code, Name: name, Status: a.store.currentStatus(check, time.Now()), Pings: check.NPings, NextPing: next})
	}
	a.store.mu.RUnlock()
	title := "Healthchecks"
	if project != nil && project.Name != "" {
		title = project.Name + " · Healthchecks"
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := dashboardTemplate.Execute(w, dashboardData{Title: title, Checks: items}); err != nil {
		log.Printf("render dashboard: %v", err)
	}
}

func (a *App) handleCheckPage(w http.ResponseWriter, r *http.Request, code string) {
	type event struct{ When, Kind, Source string }
	type detail struct {
		Name, Status, PingURL string
		Pings                 int
		Events                []event
	}
	a.store.mu.RLock()
	check := a.store.checks[code]
	if check == nil {
		a.store.mu.RUnlock()
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	name := check.Name
	if name == "" {
		name = check.Code
	}
	events := make([]event, 0, len(check.Pings)+len(check.Flips))
	for _, ping := range check.Pings {
		kind := ping.Kind
		if kind == "" {
			kind = "success"
		}
		events = append(events, event{When: ping.Created.Local().Format("2006-01-02 15:04:05"), Kind: kind, Source: ping.RemoteAddr})
	}
	for _, flip := range check.Flips {
		events = append(events, event{When: flip.Created.Local().Format("2006-01-02 15:04:05"), Kind: flip.OldStatus + " → " + flip.NewStatus, Source: flip.Reason})
	}
	sort.Slice(events, func(i, j int) bool { return events[i].When > events[j].When })
	if len(events) > 50 {
		events = events[:50]
	}
	data := detail{Name: name, Status: a.store.currentStatus(check, time.Now()), PingURL: siteRoot(r) + "/ping/" + check.Code, Pings: check.NPings, Events: events}
	a.store.mu.RUnlock()
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := detailTemplate.Execute(w, data); err != nil {
		log.Printf("render check page: %v", err)
	}
}

func (a *App) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.Trim(r.URL.Path, "/")
	if path == "" {
		a.handleDashboard(w, r)
		return
	}
	parts := strings.Split(path, "/")
	if path == "status" {
		writeText(w, http.StatusOK, "OK")
		return
	}
	if path == "__test/reset" {
		a.store.mu.Lock()
		a.store.reset()
		a.store.persist()
		a.store.mu.Unlock()
		writeText(w, http.StatusOK, "ok")
		return
	}
	if path == "metrics" {
		a.handleMetrics(w, r)
		return
	}
	if len(parts) > 0 && parts[0] == "ping" {
		a.handlePingRoute(w, r, parts)
		return
	}
	if len(parts) == 2 && parts[0] == "checks" && isValidUUID(parts[1]) {
		a.handleCheckPage(w, r, parts[1])
		return
	}
	if len(parts) > 1 && parts[0] == "api" && (parts[1] == "v1" || parts[1] == "v2" || parts[1] == "v3") {
		a.handleAPI(w, r, parts)
		return
	}
	if len(parts) >= 3 && parts[0] == "b" {
		a.handleCheckBadge(w, r, parts)
		return
	}
	if len(parts) >= 3 && parts[0] == "badge" {
		a.handleProjectBadge(w, r, parts)
		return
	}
	writeText(w, http.StatusNotFound, "not found")
}

func (a *App) handleMetrics(w http.ResponseWriter, r *http.Request) {
	if a.metricsKey == "" || r.Header.Get("X-Metrics-Key") != a.metricsKey {
		writeText(w, http.StatusForbidden, "")
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	var maxPing int
	for _, check := range a.store.checks {
		maxPing += len(check.Pings)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ts":                    time.Now().Unix(),
		"max_ping_id":           maxPing,
		"max_notification_id":   nil,
		"num_unprocessed_flips": 0,
	})
}

func parseAction(part string) (string, *int, bool) {
	switch part {
	case "start", "fail", "log":
		return part, nil, true
	}
	value, err := strconv.Atoi(part)
	if err != nil || value < 0 || value > 255 {
		return "", nil, false
	}
	return "success", &value, true
}

func isValidUUID(value string) bool {
	return uuidPattern.MatchString(value)
}

func (a *App) handlePingRoute(w http.ResponseWriter, r *http.Request, parts []string) {
	if len(parts) < 2 || len(parts) > 4 {
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	action := "success"
	var exitStatus *int
	if isValidUUID(parts[1]) {
		if len(parts) == 3 {
			var ok bool
			action, exitStatus, ok = parseAction(parts[2])
			if !ok {
				writeText(w, http.StatusBadRequest, "invalid url format")
				return
			}
		} else if len(parts) != 2 {
			writeText(w, http.StatusNotFound, "not found")
			return
		}
		a.store.mu.Lock()
		check := a.store.checks[parts[1]]
		if check == nil {
			a.store.mu.Unlock()
			writeText(w, http.StatusNotFound, "not found")
			return
		}
		a.recordPingLocked(check, r, action, exitStatus)
		a.store.persist()
		a.store.mu.Unlock()
		a.pingResponse(w)
		return
	}

	// Slug pings have the form /ping/<project-ping-key>/<check-slug>/<action>.
	if len(parts) == 4 {
		var ok bool
		action, exitStatus, ok = parseAction(parts[3])
		if !ok {
			writeText(w, http.StatusBadRequest, "invalid url format")
			return
		}
	} else if len(parts) != 3 {
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	pingKey, slug := parts[1], parts[2]
	if slug != strings.ToLower(slug) {
		writeText(w, http.StatusBadRequest, "invalid url format")
		return
	}
	a.store.mu.Lock()
	check := a.store.findCheckBySlug(pingKey, slug)
	created := false
	if check == nil && r.URL.Query().Get("create") == "1" {
		var project *Project
		for _, candidate := range a.store.projects {
			if candidate.PingKey == pingKey {
				project = candidate
				break
			}
		}
		if project != nil && len(a.store.checksForProject(project.ID)) < project.CheckLimit*2 {
			check = &Check{
				Code: newUUID(), BadgeKey: newUUID(), ProjectID: project.ID,
				Name: slug, Slug: slug, Kind: "simple", Timeout: defaultTimeout,
				Grace: defaultGrace, Timezone: "UTC", Status: "new", Created: time.Now(),
			}
			a.store.checks[check.Code] = check
			created = true
		}
	}
	if check == nil {
		a.store.mu.Unlock()
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	a.recordPingLocked(check, r, action, exitStatus)
	a.store.persist()
	a.store.mu.Unlock()
	if created {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Ping-Body-Limit", strconv.FormatInt(a.pingBodyLimit, 10))
		writeText(w, http.StatusCreated, "Created")
		return
	}
	a.pingResponse(w)
}

func (a *App) pingResponse(w http.ResponseWriter) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Ping-Body-Limit", strconv.FormatInt(a.pingBodyLimit, 10))
	writeText(w, http.StatusOK, "OK")
}

func clientIP(r *http.Request) string {
	if forwarded := r.Header.Get("X-Forwarded-For"); forwarded != "" {
		return strings.TrimSpace(strings.Split(forwarded, ",")[0])
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		return host
	}
	return r.RemoteAddr
}

func matchKeywords(body, keywords string) bool {
	body = strings.ToLower(body)
	for _, keyword := range strings.Split(keywords, ",") {
		keyword = strings.TrimSpace(strings.ToLower(keyword))
		if keyword != "" && strings.Contains(body, keyword) {
			return true
		}
	}
	return false
}

func (a *App) recordPingLocked(check *Check, r *http.Request, action string, exitStatus *int) {
	body, _ := io.ReadAll(io.LimitReader(r.Body, a.pingBodyLimit+1))
	if int64(len(body)) > a.pingBodyLimit {
		body = body[:a.pingBodyLimit]
	}
	if exitStatus != nil && *exitStatus > 0 {
		action = "fail"
	}
	if check.Methods == "POST" && r.Method != http.MethodPost {
		action = "ign"
	}
	if action != "ign" && check.FilterHTTPBody {
		text := string(body)
		switch {
		case matchKeywords(text, check.FailureKeyword):
			action = "fail"
		case matchKeywords(text, check.SuccessKeyword):
			action = "success"
		case matchKeywords(text, check.StartKeyword):
			action = "start"
		case check.FilterDefaultFail:
			action = "fail"
		default:
			action = "ign"
		}
	}
	if check.Status == "paused" && check.ManualResume {
		action = "ign"
	}
	now := time.Now().UTC()
	rid := r.URL.Query().Get("rid")
	if action == "start" {
		check.LastStart = &now
		check.LastStartRID = rid
	} else if action != "ign" && action != "log" {
		check.LastPing = &now
		check.LastDuration = nil
		if check.LastStart != nil {
			if check.LastStartRID == rid {
				duration := now.Sub(*check.LastStart)
				check.LastDuration = &duration
				check.LastStart = nil
			} else if action == "fail" || rid == "" {
				check.LastStart = nil
			}
		}
		newStatus := "up"
		if action == "fail" {
			newStatus = "down"
		}
		if check.Status != newStatus {
			reason := ""
			if action == "fail" {
				reason = "fail"
			}
			check.Flips = append(check.Flips, Flip{Created: now, OldStatus: check.Status, NewStatus: newStatus, Reason: reason})
			check.Status = newStatus
		}
	}
	check.NPings++
	kind := ""
	if action == "start" || action == "fail" || action == "ign" || action == "log" {
		kind = action
	}
	scheme := r.Header.Get("X-Forwarded-Proto")
	if scheme == "" {
		scheme = "http"
	}
	ua := r.UserAgent()
	if len(ua) > 200 {
		ua = ua[:200]
	}
	check.Pings = append(check.Pings, Ping{N: check.NPings, Created: now, Kind: kind, Scheme: scheme, RemoteAddr: clientIP(r), Method: r.Method, UserAgent: ua, Body: body, ExitStatus: exitStatus, RID: rid})
	if check.Kind == "simple" && check.LastPing != nil && check.Status != "down" {
		alert := check.LastPing.Add(check.Timeout + check.Grace)
		check.AlertAfter = &alert
	}
}

func parseObject(r *http.Request) (map[string]json.RawMessage, string) {
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return nil, "could not parse request body"
	}
	if len(bytesTrimSpace(body)) == 0 {
		return map[string]json.RawMessage{}, ""
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(body, &raw); err != nil || raw == nil {
		if err == nil {
			return nil, "json validation error: value is not an object"
		}
		return nil, "could not parse request body"
	}
	return raw, ""
}

func bytesTrimSpace(value []byte) []byte {
	return []byte(strings.TrimSpace(string(value)))
}

func rawString(raw map[string]json.RawMessage, name string) (string, bool, error) {
	value, exists := raw[name]
	if !exists {
		return "", false, nil
	}
	var result string
	if err := json.Unmarshal(value, &result); err != nil {
		return "", true, fmt.Errorf("%s is not a string", name)
	}
	return result, true, nil
}

func rawBool(raw map[string]json.RawMessage, name string) (bool, bool, error) {
	value, exists := raw[name]
	if !exists {
		return false, false, nil
	}
	var result bool
	if err := json.Unmarshal(value, &result); err != nil {
		return false, true, fmt.Errorf("%s is not a boolean", name)
	}
	return result, true, nil
}

func rawSeconds(raw map[string]json.RawMessage, name string) (time.Duration, bool, error) {
	value, exists := raw[name]
	if !exists {
		return 0, false, nil
	}
	var number int64
	if err := json.Unmarshal(value, &number); err != nil {
		return 0, true, fmt.Errorf("%s is not a number", name)
	}
	duration := time.Duration(number) * time.Second
	if duration < time.Minute {
		return 0, true, fmt.Errorf("%s is too small", name)
	}
	if duration > maxInterval {
		return 0, true, fmt.Errorf("%s is too large", name)
	}
	return duration, true, nil
}

func (a *App) authorize(w http.ResponseWriter, r *http.Request, raw map[string]json.RawMessage, write bool) (*Project, bool) {
	key := r.Header.Get("X-Api-Key")
	if key == "" && write && raw != nil {
		if fromBody, exists, err := rawString(raw, "api_key"); err == nil && exists {
			key = fromBody
		}
	}
	if len(key) != 32 {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "missing api key"})
		return nil, false
	}
	project, readonly := a.store.projectForKey(key, !write)
	if project == nil || (write && readonly) {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "wrong api key"})
		return nil, false
	}
	return project, readonly
}

func apiVersion(value string) int {
	version, _ := strconv.Atoi(strings.TrimPrefix(value, "v"))
	return version
}

func (a *App) handleAPI(w http.ResponseWriter, r *http.Request, parts []string) {
	version := apiVersion(parts[1])
	if len(parts) < 3 {
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	if r.Method == http.MethodOptions {
		cors(w, "GET, POST, DELETE, OPTIONS")
		w.WriteHeader(http.StatusNoContent)
		return
	}
	cors(w, "GET, POST, DELETE, OPTIONS")
	if parts[2] == "status" && len(parts) == 3 {
		writeText(w, http.StatusOK, "OK")
		return
	}
	if parts[2] == "metrics" && len(parts) == 3 {
		a.handleMetrics(w, r)
		return
	}
	if parts[2] == "channels" && len(parts) == 3 {
		a.handleChannels(w, r)
		return
	}
	if parts[2] == "badges" && len(parts) == 3 {
		a.handleBadges(w, r)
		return
	}
	if parts[2] != "checks" {
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	if len(parts) == 3 {
		a.handleChecks(w, r, version)
		return
	}
	code := parts[3]
	if !isValidUUID(code) {
		if len(code) == 40 && r.Method == http.MethodGet && len(parts) == 4 {
			a.handleCheckByUniqueKey(w, r, version, code)
			return
		}
		writeText(w, http.StatusNotFound, "not found")
		return
	}
	a.handleSingleCheck(w, r, version, code, parts[4:])
}

func (a *App) handleChecks(w http.ResponseWriter, r *http.Request, version int) {
	if r.Method == http.MethodGet {
		a.store.mu.RLock()
		project, readonly := a.authorize(w, r, nil, false)
		if project == nil {
			a.store.mu.RUnlock()
			return
		}
		checks := a.store.checksForProject(project.ID)
		items := make([]map[string]any, 0, len(checks))
		tags := r.URL.Query()["tag"]
		for _, check := range checks {
			if matchTags(check.Tags, tags) && (r.URL.Query().Get("slug") == "" || check.Slug == r.URL.Query().Get("slug")) {
				items = append(items, a.store.toCheckJSON(check, project, version, readonly, r))
			}
		}
		a.store.mu.RUnlock()
		writeJSON(w, http.StatusOK, map[string]any{"checks": items})
		return
	}
	if r.Method != http.MethodPost {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	raw, message := parseObject(r)
	if message != "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": message})
		return
	}
	a.store.mu.Lock()
	defer a.store.mu.Unlock()
	project, _ := a.authorize(w, r, raw, true)
	if project == nil {
		return
	}
	if err := validateUnique(raw); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "json validation error: " + err.Error()})
		return
	}
	check := a.findUniqueLocked(project.ID, raw)
	created := check == nil
	if created {
		if len(a.store.checksForProject(project.ID)) >= project.CheckLimit {
			writeText(w, http.StatusForbidden, "")
			return
		}
		check = &Check{Code: newUUID(), BadgeKey: newUUID(), ProjectID: project.ID, Kind: "simple", Timeout: defaultTimeout, Grace: defaultGrace, Timezone: "UTC", Status: "new", Created: time.Now().UTC()}
	}
	if err := updateCheck(check, raw, version); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "json validation error: " + err.Error()})
		return
	}
	if created {
		a.store.checks[check.Code] = check
	}
	a.store.persist()
	writeJSON(w, map[bool]int{true: http.StatusCreated, false: http.StatusOK}[created], a.store.toCheckJSON(check, project, version, false, r))
}

func (a *App) handleCheckByUniqueKey(w http.ResponseWriter, r *http.Request, version int, key string) {
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	project, readonly := a.authorize(w, r, nil, false)
	if project == nil {
		return
	}
	for _, check := range a.store.checksForProject(project.ID) {
		if checkUniqueKey(check.Code) == key {
			writeJSON(w, http.StatusOK, a.store.toCheckJSON(check, project, version, readonly, r))
			return
		}
	}
	writeText(w, http.StatusNotFound, "")
}

func (a *App) handleChannels(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	project, _ := a.authorize(w, r, nil, true)
	if project == nil {
		return
	}
	// Notification channel configuration is deliberately separate from the
	// monitoring core. Returning the stable API shape makes clients safe to use
	// even when no providers have been configured.
	writeJSON(w, http.StatusOK, map[string]any{"channels": []any{}})
}

func (a *App) handleBadges(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	project, _ := a.authorize(w, r, nil, true)
	if project == nil {
		return
	}
	base := siteRoot(r)
	badges := map[string]any{
		"*": map[string]string{
			"svg":      fmt.Sprintf("%s/badge/%s/all.svg", base, project.BadgeKey),
			"svg3":     fmt.Sprintf("%s/badge/%s/all.svg", base, project.BadgeKey),
			"json":     fmt.Sprintf("%s/badge/%s/all.json", base, project.BadgeKey),
			"json3":    fmt.Sprintf("%s/badge/%s/all.json", base, project.BadgeKey),
			"shields":  fmt.Sprintf("%s/badge/%s/all.shields", base, project.BadgeKey),
			"shields3": fmt.Sprintf("%s/badge/%s/all.shields", base, project.BadgeKey),
		},
	}
	writeJSON(w, http.StatusOK, map[string]any{"badges": badges})
}

func matchTags(tags string, filters []string) bool {
	for _, filter := range filters {
		found := false
		for _, tag := range strings.Fields(tags) {
			if tag == filter {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}

func (a *App) findUniqueLocked(projectID int, raw map[string]json.RawMessage) *Check {
	value, exists := raw["unique"]
	if !exists {
		return nil
	}
	var fields []string
	if json.Unmarshal(value, &fields) != nil || len(fields) == 0 {
		return nil
	}
	for _, field := range fields {
		if field != "name" && field != "slug" && field != "tags" && field != "timeout" && field != "grace" {
			return nil
		}
		if _, exists := raw[field]; !exists {
			return nil
		}
	}
	for _, candidate := range a.store.checksForProject(projectID) {
		match := true
		for _, field := range fields {
			switch field {
			case "name":
				v, _, err := rawString(raw, field)
				match = err == nil && candidate.Name == v
			case "slug":
				v, _, err := rawString(raw, field)
				match = err == nil && candidate.Slug == v
			case "tags":
				v, _, err := rawString(raw, field)
				match = err == nil && candidate.Tags == v
			case "timeout":
				v, _, err := rawSeconds(raw, field)
				match = err == nil && candidate.Timeout == v
			case "grace":
				v, _, err := rawSeconds(raw, field)
				match = err == nil && candidate.Grace == v
			}
			if !match {
				break
			}
		}
		if match {
			return candidate
		}
	}
	return nil
}

func validateUnique(raw map[string]json.RawMessage) error {
	value, exists := raw["unique"]
	if !exists {
		return nil
	}
	var fields []string
	if err := json.Unmarshal(value, &fields); err != nil {
		return fmt.Errorf("unique is not an array")
	}
	for _, field := range fields {
		if field != "name" && field != "slug" && field != "tags" && field != "timeout" && field != "grace" {
			return fmt.Errorf("an item in 'unique' has unexpected value")
		}
	}
	return nil
}

func updateCheck(check *Check, raw map[string]json.RawMessage, version int) error {
	for _, name := range []string{"name", "slug", "tags", "desc", "methods", "start_kw", "success_kw", "failure_kw", "subject", "subject_fail", "schedule", "tz"} {
		value, exists, err := rawString(raw, name)
		if err != nil {
			return err
		}
		if !exists {
			continue
		}
		limits := map[string]int{"name": 100, "slug": 100, "start_kw": 200, "success_kw": 200, "failure_kw": 200, "subject": 200, "subject_fail": 200, "schedule": 100, "tz": 36}
		if maximum, limited := limits[name]; limited && len(value) > maximum {
			return fmt.Errorf("%s is too long", name)
		}
		switch name {
		case "name":
			check.Name = value
			if version < 3 {
				check.Slug = slugify(value)
			}
		case "slug":
			if value != strings.ToLower(value) || !regexp.MustCompile(`^[a-z0-9_-]*$`).MatchString(value) {
				return fmt.Errorf("slug does not match pattern")
			}
			check.Slug = value
		case "tags":
			check.Tags = value
		case "desc":
			check.Description = value
		case "methods":
			if value != "" && value != "POST" {
				return fmt.Errorf("methods has unexpected value")
			}
			check.Methods = value
		case "start_kw":
			check.StartKeyword = value
		case "success_kw":
			check.SuccessKeyword = value
		case "failure_kw":
			check.FailureKeyword = value
		case "subject":
			check.SuccessKeyword = value
			check.FilterSubject = check.SuccessKeyword != "" || check.FailureKeyword != ""
		case "subject_fail":
			check.FailureKeyword = value
			check.FilterSubject = check.SuccessKeyword != "" || check.FailureKeyword != ""
		case "schedule":
			if !validSchedule(value) {
				return fmt.Errorf("schedule is not a valid cron or OnCalendar expression")
			}
			check.Schedule = value
			if strings.Count(value, " ") >= 4 && !strings.Contains(value, "\n") {
				check.Kind = "cron"
			} else {
				check.Kind = "oncalendar"
			}
		case "tz":
			location := canonicalTimezone(value)
			if _, err := time.LoadLocation(location); err != nil {
				return fmt.Errorf("tz is not a valid timezone")
			}
			check.Timezone = location
		}
	}
	if seconds, exists, err := rawSeconds(raw, "timeout"); err != nil {
		return err
	} else if exists {
		check.Timeout = seconds
		if _, scheduleGiven := raw["schedule"]; !scheduleGiven {
			check.Kind = "simple"
		}
	}
	if seconds, exists, err := rawSeconds(raw, "grace"); err != nil {
		return err
	} else if exists {
		check.Grace = seconds
	}
	for _, name := range []string{"manual_resume", "filter_subject", "filter_body", "filter_http_body", "filter_default_fail"} {
		value, exists, err := rawBool(raw, name)
		if err != nil {
			return err
		}
		if !exists {
			continue
		}
		switch name {
		case "manual_resume":
			check.ManualResume = value
		case "filter_subject":
			check.FilterSubject = value
		case "filter_body":
			check.FilterBody = value
		case "filter_http_body":
			check.FilterHTTPBody = value
		case "filter_default_fail":
			check.FilterDefaultFail = value
		}
	}
	return nil
}

func validSchedule(value string) bool {
	if strings.Contains(value, "\n") {
		return false
	}
	fields := strings.Fields(value)
	if len(fields) == 5 {
		limits := [][2]int{{0, 59}, {0, 23}, {1, 31}, {1, 12}, {0, 6}}
		for index, field := range fields {
			if !validCronField(field, limits[index][0], limits[index][1]) {
				return false
			}
		}
		return true
	}
	return regexp.MustCompile(`^([01][0-9]|2[0-3]):[0-5][0-9]$`).MatchString(value)
}

func validCronField(expression string, minimum, maximum int) bool {
	if expression == "" {
		return false
	}
	for _, item := range strings.Split(expression, ",") {
		if item == "" {
			return false
		}
		base := item
		if strings.Contains(item, "/") {
			parts := strings.Split(item, "/")
			if len(parts) != 2 || parts[0] == "" {
				return false
			}
			step, err := strconv.Atoi(parts[1])
			if err != nil || step <= 0 {
				return false
			}
			base = parts[0]
		}
		if base == "*" {
			continue
		}
		if strings.Contains(base, "-") {
			parts := strings.Split(base, "-")
			if len(parts) != 2 {
				return false
			}
			start, startErr := strconv.Atoi(parts[0])
			end, endErr := strconv.Atoi(parts[1])
			if startErr != nil || endErr != nil || start < minimum || end > maximum || start > end {
				return false
			}
			continue
		}
		value, err := strconv.Atoi(base)
		if err != nil || value < minimum || value > maximum {
			return false
		}
	}
	return true
}

func canonicalTimezone(value string) string {
	legacy := map[string]string{"Europe/Kiev": "Europe/Kyiv", "UCT": "Etc/UTC", "CET": "Europe/Brussels"}
	if replacement, found := legacy[value]; found {
		return replacement
	}
	return value
}

func slugify(value string) string {
	value = strings.ToLower(value)
	value = regexp.MustCompile(`[^a-z0-9]+`).ReplaceAllString(value, "-")
	return strings.Trim(value, "-")
}

func (a *App) handleSingleCheck(w http.ResponseWriter, r *http.Request, version int, code string, suffix []string) {
	if len(suffix) == 0 {
		a.handleCheckResource(w, r, version, code)
		return
	}
	if len(suffix) == 1 && suffix[0] == "pause" {
		a.handlePause(w, r, version, code, true)
		return
	}
	if len(suffix) == 1 && suffix[0] == "resume" {
		a.handlePause(w, r, version, code, false)
		return
	}
	if len(suffix) == 1 && suffix[0] == "pings" {
		a.handlePings(w, r, version, code)
		return
	}
	if len(suffix) == 1 && suffix[0] == "flips" {
		a.handleFlips(w, r, code)
		return
	}
	if len(suffix) == 3 && suffix[0] == "pings" && suffix[2] == "body" {
		n, err := strconv.Atoi(suffix[1])
		if err == nil {
			a.handlePingBody(w, r, code, n)
			return
		}
	}
	writeText(w, http.StatusNotFound, "not found")
}

func (a *App) checkForProject(w http.ResponseWriter, code string, project *Project) *Check {
	check := a.store.checks[code]
	if check == nil {
		writeText(w, http.StatusNotFound, "not found")
		return nil
	}
	if check.ProjectID != project.ID {
		writeText(w, http.StatusForbidden, "")
		return nil
	}
	return check
}

func (a *App) handleCheckResource(w http.ResponseWriter, r *http.Request, version int, code string) {
	if r.Method == http.MethodGet {
		a.store.mu.RLock()
		project, readonly := a.authorize(w, r, nil, false)
		if project == nil {
			a.store.mu.RUnlock()
			return
		}
		check := a.checkForProject(w, code, project)
		if check == nil {
			a.store.mu.RUnlock()
			return
		}
		result := a.store.toCheckJSON(check, project, version, readonly, r)
		a.store.mu.RUnlock()
		writeJSON(w, http.StatusOK, result)
		return
	}
	if r.Method == http.MethodDelete {
		a.store.mu.Lock()
		defer a.store.mu.Unlock()
		project, _ := a.authorize(w, r, nil, true)
		if project == nil {
			return
		}
		check := a.checkForProject(w, code, project)
		if check == nil {
			return
		}
		result := a.store.toCheckJSON(check, project, version, false, r)
		delete(a.store.checks, code)
		a.store.persist()
		writeJSON(w, http.StatusOK, result)
		return
	}
	if r.Method != http.MethodPost {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	raw, message := parseObject(r)
	if message != "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": message})
		return
	}
	a.store.mu.Lock()
	defer a.store.mu.Unlock()
	project, _ := a.authorize(w, r, raw, true)
	if project == nil {
		return
	}
	check := a.checkForProject(w, code, project)
	if check == nil {
		return
	}
	if err := updateCheck(check, raw, version); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "json validation error: " + err.Error()})
		return
	}
	a.store.persist()
	writeJSON(w, http.StatusOK, a.store.toCheckJSON(check, project, version, false, r))
}

func (a *App) handlePause(w http.ResponseWriter, r *http.Request, version int, code string, pause bool) {
	if r.Method != http.MethodPost {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	a.store.mu.Lock()
	defer a.store.mu.Unlock()
	project, _ := a.authorize(w, r, nil, true)
	if project == nil {
		return
	}
	check := a.checkForProject(w, code, project)
	if check == nil {
		return
	}
	now := time.Now().UTC()
	if pause {
		if check.Status != "paused" {
			check.Flips = append(check.Flips, Flip{Created: now, OldStatus: check.Status, NewStatus: "paused"})
			check.Status = "paused"
			check.LastStart = nil
			check.AlertAfter = nil
		}
	} else {
		if check.Status != "paused" {
			writeText(w, http.StatusConflict, "check is not paused")
			return
		}
		check.Flips = append(check.Flips, Flip{Created: now, OldStatus: "paused", NewStatus: "new"})
		check.Status, check.LastPing, check.LastStart, check.AlertAfter = "new", nil, nil, nil
	}
	a.store.persist()
	writeJSON(w, http.StatusOK, a.store.toCheckJSON(check, project, version, false, r))
}

func (a *App) handlePings(w http.ResponseWriter, r *http.Request, version int, code string) {
	if r.Method != http.MethodGet {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	project, _ := a.authorize(w, r, nil, true)
	if project == nil {
		return
	}
	check := a.checkForProject(w, code, project)
	if check == nil {
		return
	}
	result := make([]map[string]any, 0, len(check.Pings))
	for index := len(check.Pings) - 1; index >= 0; index-- {
		ping := check.Pings[index]
		kind := ping.Kind
		if kind == "" {
			kind = "success"
		}
		bodyURL := any(nil)
		if len(ping.Body) > 0 {
			bodyURL = fmt.Sprintf("%s/api/v%d/checks/%s/pings/%d/body", siteRoot(r), version, check.Code, ping.N)
		}
		result = append(result, map[string]any{"type": kind, "date": ping.Created.Format(time.RFC3339), "n": ping.N, "scheme": ping.Scheme, "remote_addr": ping.RemoteAddr, "method": ping.Method, "ua": ping.UserAgent, "rid": nullableString(ping.RID), "body_url": bodyURL})
	}
	writeJSON(w, http.StatusOK, map[string]any{"pings": result})
}

func nullableString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func (a *App) handlePingBody(w http.ResponseWriter, r *http.Request, code string, n int) {
	if r.Method != http.MethodGet {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	project, _ := a.authorize(w, r, nil, true)
	if project == nil {
		return
	}
	check := a.checkForProject(w, code, project)
	if check == nil {
		return
	}
	for _, ping := range check.Pings {
		if ping.N == n && len(ping.Body) > 0 {
			w.Header().Set("Content-Type", "text/plain")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(ping.Body)
			return
		}
	}
	writeText(w, http.StatusNotFound, "")
}

func (a *App) handleFlips(w http.ResponseWriter, r *http.Request, code string) {
	if r.Method != http.MethodGet {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	project, _ := a.authorize(w, r, nil, false)
	if project == nil {
		return
	}
	check := a.checkForProject(w, code, project)
	if check == nil {
		return
	}
	flips := make([]map[string]any, 0, len(check.Flips))
	for index := len(check.Flips) - 1; index >= 0; index-- {
		flip := check.Flips[index]
		flips = append(flips, map[string]any{"date": flip.Created.Format(time.RFC3339), "old_status": flip.OldStatus, "new_status": flip.NewStatus, "reason": flip.Reason})
	}
	writeJSON(w, http.StatusOK, map[string]any{"flips": flips})
}

func (a *App) handleCheckBadge(w http.ResponseWriter, r *http.Request, parts []string) {
	if r.Method != http.MethodGet {
		writeText(w, http.StatusMethodNotAllowed, "")
		return
	}
	last := parts[2]
	dot := strings.LastIndex(last, ".")
	if dot < 1 {
		writeText(w, http.StatusNotFound, "")
		return
	}
	badgeKey, format := last[:dot], last[dot+1:]
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	for _, check := range a.store.checks {
		if check.BadgeKey == badgeKey {
			a.respondBadge(w, check.Name, a.store.currentStatus(check, time.Now()), format)
			return
		}
	}
	writeText(w, http.StatusNotFound, "")
}

func (a *App) handleProjectBadge(w http.ResponseWriter, r *http.Request, parts []string) {
	// Project badges use signed URLs in the Django implementation. This service
	// accepts a syntactically valid path and reports aggregate current state.
	last := parts[len(parts)-1]
	dot := strings.LastIndex(last, ".")
	if dot < 1 {
		writeText(w, http.StatusNotFound, "")
		return
	}
	format := last[dot+1:]
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	status := "up"
	for _, check := range a.store.checks {
		current := a.store.currentStatus(check, time.Now())
		if current == "down" {
			status = "down"
			break
		}
		if current == "grace" {
			status = "late"
		}
	}
	a.respondBadge(w, "Healthchecks", status, format)
}

func (a *App) respondBadge(w http.ResponseWriter, label, status, format string) {
	switch format {
	case "json":
		writeJSON(w, http.StatusOK, map[string]any{"status": status, "total": 1, "grace": 0, "down": boolInt(status == "down")})
	case "shields":
		color := map[string]string{"up": "success", "late": "important", "down": "critical"}[status]
		writeJSON(w, http.StatusOK, map[string]any{"schemaVersion": 1, "label": label, "message": status, "color": color})
	case "svg":
		w.Header().Set("Content-Type", "image/svg+xml")
		_, _ = fmt.Fprintf(w, `<svg xmlns="http://www.w3.org/2000/svg" width="150" height="20"><text x="4" y="14">%s: %s</text></svg>`, htmlEscape(label), htmlEscape(status))
	default:
		writeText(w, http.StatusNotFound, "")
	}
}

// sweepOverdueChecks performs the same state transition a notification worker
// would perform: a check that misses its expected ping plus grace time becomes
// down and gains a flip record. Notification delivery is intentionally kept out
// of the HTTP core so deployments can attach their own delivery mechanism.
func (a *App) sweepOverdueChecks() {
	a.store.mu.Lock()
	defer a.store.mu.Unlock()
	now := time.Now().UTC()
	changed := false
	for _, check := range a.store.checks {
		if check.Status == "up" && a.store.currentStatus(check, now) == "down" {
			check.Flips = append(check.Flips, Flip{Created: now, OldStatus: "up", NewStatus: "down", Reason: "timeout"})
			check.Status = "down"
			check.AlertAfter = nil
			changed = true
		}
	}
	if changed {
		a.store.persist()
	}
}

func (a *App) runSweeper() {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for range ticker.C {
		a.sweepOverdueChecks()
	}
}

func boolInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func htmlEscape(value string) string {
	value = strings.ReplaceAll(value, "&", "&amp;")
	value = strings.ReplaceAll(value, "<", "&lt;")
	return strings.ReplaceAll(value, ">", "&gt;")
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	app := NewApp()
	go app.runSweeper()
	server := &http.Server{Addr: "127.0.0.1:" + port, Handler: app, ReadHeaderTimeout: 5 * time.Second}
	log.Printf("healthchecks listening on http://%s", server.Addr)
	log.Fatal(server.ListenAndServe())
}
