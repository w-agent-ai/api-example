package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	defaultBaseURL = "https://www.w-agent.cn/api"
	defaultAPIKey  = "gak_your_api_key"
	timeout        = 120 * time.Second
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: %s /path/to/image.jpg\n", os.Args[0])
		os.Exit(2)
	}
	apiKey := strings.TrimSpace(defaultAPIKey)
	if apiKey == "" || apiKey == "gak_your_api_key" {
		fmt.Fprintln(os.Stderr, "edit defaultAPIKey in main.go before running this demo")
		os.Exit(2)
	}
	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	payload, _ := json.Marshal(map[string]any{
		"image_base64":    base64.StdEncoding.EncodeToString(data),
		"idempotency_key": filepath.Clean(os.Args[1]),
	})
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(defaultBaseURL, "/")+"/v1/features/reid", bytes.NewReader(payload))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)
	client := &http.Client{Timeout: timeout}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("status=%d\n%s\n", resp.StatusCode, string(body))
	if resp.StatusCode >= 400 {
		os.Exit(1)
	}
}
