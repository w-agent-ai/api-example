package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	// Official API base URL. Keep /api when using the hosted service.
	defaultBaseURL = "https://www.w-agent.cn/api"
	// Replace this placeholder with an active registered-user API Key.
	defaultAPIKey = "gak_your_api_key"
)

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintf(os.Stderr, "Usage: %s /path/to/image.jpg \"prompt\"\n", os.Args[0])
		os.Exit(2)
	}
	if strings.TrimSpace(defaultAPIKey) == "" || defaultAPIKey == "gak_your_api_key" {
		fmt.Fprintln(os.Stderr, "edit defaultAPIKey in main.go before running this demo")
		os.Exit(2)
	}
	image, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	// The API accepts raw Base64 without a data:image/... prefix.
	payload, err := json.Marshal(map[string]string{
		"image_base64": base64.StdEncoding.EncodeToString(image),
		"prompt":       os.Args[2],
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(defaultBaseURL, "/")+"/v1/object-search", bytes.NewReader(payload))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+defaultAPIKey)
	resp, err := (&http.Client{Timeout: 120 * time.Second}).Do(req)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("status=%d\n%s\n", resp.StatusCode, body)
	if resp.StatusCode >= http.StatusBadRequest {
		os.Exit(1)
	}
}
