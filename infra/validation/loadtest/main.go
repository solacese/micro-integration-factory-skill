package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"go.yaml.in/yaml/v3"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type configuration struct {
	Broker struct {
		SMFURL   string `yaml:"smf-url"`
		VPN      string `yaml:"vpn"`
		AMQPURL  string `yaml:"amqp-url"`
		Username string `yaml:"username"`
		Password string `yaml:"password"`
	} `yaml:"broker"`
	Messaging struct {
		InputTopic  string `yaml:"input-topic"`
		OutputTopic string `yaml:"output-topic"`
	} `yaml:"messaging"`
	Webhook struct {
		Provider      string `yaml:"provider"`
		SigningSecret string `yaml:"signing-secret"`
	} `yaml:"webhook"`
}
type example struct {
	Input   string         `json:"input_base64"`
	Output  *string        `json:"output_base64"`
	Topics  []string       `json:"output_topics"`
	Headers map[string]any `json:"headers"`
}
type event struct {
	start     time.Time
	end       time.Time
	mask      uint32
	errors    int
	duplicate int
	lag       float64
}

func main() {
	configPath := flag.String("config", "config/mi-demo.yaml", "")
	examplesPath := flag.String("examples", "core-examples.json", "")
	endpoint := flag.String("http", "http://integration:8080/ingest", "")
	out := flag.String("output", "benchmark.json", "")
	target := flag.Int("rate", 1000, "")
	seconds := flag.Int("seconds", 10, "")
	protocol := flag.String("transport", "amqp", "broker wire protocol")
	warmSeconds := flag.Int("warmup", 3, "")
	flag.Parse()
	if err := run(*configPath, *examplesPath, *endpoint, *out, *target, *seconds, *warmSeconds, *protocol); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run(configPath, examplesPath, endpoint, out string, target, seconds, warmSeconds int, protocol string) error {
	if target < 1 || seconds < 1 {
		return fmt.Errorf("invalid load settings")
	}
	raw, err := os.ReadFile(configPath)
	if err != nil {
		return err
	}
	var config configuration
	if err = yaml.Unmarshal(raw, &config); err != nil {
		return err
	}
	raw, err = os.ReadFile(examplesPath)
	if err != nil {
		return err
	}
	var examples []example
	if err = json.Unmarshal(raw, &examples); err != nil {
		return err
	}
	var contract example
	for _, candidate := range examples {
		if candidate.Output != nil {
			contract = candidate
			break
		}
	}
	if contract.Output == nil {
		return fmt.Errorf("no valid contract example")
	}
	payload, err := base64.StdEncoding.DecodeString(contract.Input)
	if err != nil {
		return err
	}
	expected, err := base64.StdEncoding.DecodeString(*contract.Output)
	if err != nil {
		return err
	}
	topics := contract.Topics
	if len(topics) == 0 {
		topics = []string{config.Messaging.OutputTopic}
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(seconds+warmSeconds+45)*time.Second)
	defer cancel()
	// A small overdrive margin lets qualification require >=1000 observed deliveries/s,
	// rather than quietly rounding a below-target rate caused by tail-drain time.
	offered := int(math.Ceil(float64(target) * 1.02))
	warm := offered * warmSeconds
	count := offered * seconds
	total := warm + count
	events := make([]event, total)
	prefix := fmt.Sprintf("perf-%d-", time.Now().UnixNano())
	var mu sync.Mutex
	allMask := uint32(1<<len(topics)) - 1
	receive := func(index int, payload []byte, headers map[string]any) {
		trace, _ := headers["mi_correlation_id"].(string)
		if !strings.HasPrefix(trace, prefix) {
			return
		}
		id, err := strconv.Atoi(strings.TrimPrefix(trace, prefix))
		if err != nil || id < 0 || id >= total {
			return
		}
		mu.Lock()
		defer mu.Unlock()
		record := &events[id]
		bit := uint32(1 << index)
		if record.mask&bit != 0 {
			record.duplicate++
		}
		record.mask |= bit
		if !bytes.Equal(expected, payload) {
			record.errors++
		}
		if record.mask == allMask && record.end.IsZero() {
			record.end = time.Now()
		}
	}
	sendInput, cleanup, err := benchmarkBroker(ctx, config, protocol, topics, receive)
	if err != nil {
		return err
	}
	defer cleanup()
	brokerIngress := config.Webhook.Provider != "stripe"
	client := &http.Client{Timeout: 15 * time.Second, Transport: &http.Transport{MaxIdleConns: 256, MaxIdleConnsPerHost: 256, IdleConnTimeout: 30 * time.Second}}
	var requests sync.WaitGroup
	slots := make(chan struct{}, 256)
	start := time.Now()
	interval := time.Second / time.Duration(offered)
	for id := 0; id < total; id++ {
		scheduled := start.Add(time.Duration(id) * interval)
		if delay := time.Until(scheduled); delay > 0 {
			time.Sleep(delay)
		}
		select {
		case slots <- struct{}{}:
		case <-ctx.Done():
			return ctx.Err()
		}
		actual := time.Now()
		mu.Lock()
		events[id].start = actual
		events[id].lag = math.Max(0, float64(actual.Sub(scheduled))/float64(time.Millisecond))
		mu.Unlock()
		requests.Add(1)
		go func(id int) {
			defer requests.Done()
			defer func() { <-slots }()
			var failure error
			trace := prefix + strconv.Itoa(id)
			if brokerIngress {
				headers := map[string]any{"mi_correlation_id": trace}
				for key, value := range contract.Headers {
					headers[key] = value
				}
				failure = sendInput(ctx, payload, headers)
			} else {
				request, _ := http.NewRequestWithContext(ctx, "POST", endpoint, bytes.NewReader(payload))
				request.Header.Set("Content-Type", "application/json")
				request.Header.Set("mi_correlation_id", trace)
				timestamp := strconv.FormatInt(time.Now().Unix(), 10)
				mac := hmac.New(sha256.New, []byte(config.Webhook.SigningSecret))
				_, _ = mac.Write([]byte(timestamp + "."))
				_, _ = mac.Write(payload)
				request.Header.Set("Stripe-Signature", "t="+timestamp+",v1="+hex.EncodeToString(mac.Sum(nil)))
				response, err := client.Do(request)
				if err != nil {
					failure = err
				} else {
					_, _ = io.Copy(io.Discard, response.Body)
					_ = response.Body.Close()
					if response.StatusCode != 202 {
						failure = fmt.Errorf("http status %d", response.StatusCode)
					}
				}
			}
			if failure != nil {
				mu.Lock()
				events[id].errors++
				mu.Unlock()
			}
		}(id)
	}
	requests.Wait()
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		complete := 0
		mu.Lock()
		for id := warm; id < total; id++ {
			if !events[id].end.IsZero() {
				complete++
			}
		}
		mu.Unlock()
		if complete == count {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	cancel()
	cleanup()
	first := events[warm].start
	last := first
	delivered, failures, duplicates := 0, 0, 0
	var latency, lag []float64
	perSecond := map[int]int{}
	for id := warm; id < total; id++ {
		record := events[id]
		failures += record.errors
		duplicates += record.duplicate
		lag = append(lag, record.lag)
		if !record.end.IsZero() {
			delivered++
			latency = append(latency, float64(record.end.Sub(record.start))/float64(time.Millisecond))
			if record.end.After(last) {
				last = record.end
			}
			perSecond[int(record.end.Sub(first).Seconds())]++
		}
	}
	elapsed := measurementElapsed(seconds, first, last)
	throughput := float64(delivered) / elapsed
	peak := 0
	for _, value := range perSecond {
		if value > peak {
			peak = value
		}
	}
	statistics := func(values []float64) map[string]float64 {
		sort.Float64s(values)
		result := map[string]float64{}
		if len(values) == 0 {
			return result
		}
		sum := 0.0
		for _, value := range values {
			sum += value
		}
		result["mean"] = sum / float64(len(values))
		result["p50"] = values[int(float64(len(values)-1)*0.5)]
		result["p95"] = values[int(float64(len(values)-1)*0.95)]
		result["p99"] = values[int(float64(len(values)-1)*0.99)]
		result["max"] = values[len(values)-1]
		return result
	}
	passed := delivered == count && failures == 0 && duplicates == 0 && throughput >= float64(target)
	report := map[string]any{"passed": passed, "targetRate": target, "offeredRate": offered, "durationSeconds": seconds, "warmupSeconds": warmSeconds, "sent": count, "received": delivered, "errors": failures, "duplicates": duplicates, "payloadBytes": len(payload), "outputTopics": topics, "fanout": len(topics), "achievedRate": throughput, "peakOneSecondRate": peak, "latencyMs": statistics(latency), "generatorLagMs": statistics(lag), "elapsedSeconds": elapsed, "ingress": map[bool]string{true: "signed HTTP webhook", false: strings.ToUpper(protocol) + " input topic"}[!brokerIngress], "conditions": "isolated broker; synthetic contract fixture; 2% input overdrive; all output topics verified; not a maximum-capacity certificate"}
	data, _ := json.MarshalIndent(report, "", "  ")
	if err = os.WriteFile(out, data, 0644); err != nil {
		return err
	}
	file, err := os.Create(out + ".csv")
	if err != nil {
		return err
	}
	writer := csv.NewWriter(file)
	_ = writer.Write([]string{"id", "latency_ms", "errors", "duplicates"})
	for id := warm; id < total; id++ {
		r := events[id]
		duration := ""
		if !r.end.IsZero() {
			duration = strconv.FormatFloat(float64(r.end.Sub(r.start))/float64(time.Millisecond), 'f', 6, 64)
		}
		_ = writer.Write([]string{strconv.Itoa(id - warm), duration, strconv.Itoa(r.errors), strconv.Itoa(r.duplicate)})
	}
	writer.Flush()
	_ = file.Close()
	fmt.Println(string(data))
	if !passed {
		return fmt.Errorf("1k/s end-to-end qualification did not pass")
	}
	return nil
}

func measurementElapsed(seconds int, first, last time.Time) float64 {
	return math.Max(float64(seconds), last.Sub(first).Seconds())
}
