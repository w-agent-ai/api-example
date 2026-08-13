package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const (
	// Public API endpoint. Change this to your own deployment if needed.
	defaultBaseURL = "https://www.w-agent.cn/api"

	// Registered-user API Key. It is sent as: Authorization: Bearer <api_key>.
	// Change this value before building/running the demo.
	defaultAPIKey = "gak_your_api_key"

	// A sequence is a directory of cropped person images belonging to one track.
	// Change this value, or pass a sequence directory as the first command-line argument.
	defaultSeqDir = "./images"
	timeout       = 10 * time.Minute

	// When comparing two parsed sequences, compute face/gait/ReID dot products
	// and fuse them with fusedIdentitySimilarity. Scores above this threshold
	// are usually likely to be the same person.
	samePersonThreshold = 0.7
)

// uploadSlot is returned by POST /v1/sequences.
// The object_key is passed to /parse after batch upload completes.
type uploadSlot struct {
	Index     int    `json:"index"`
	ObjectKey string `json:"object_key"`
	UploadURL string `json:"upload_url"`
}

// createSequenceResponse contains the task id and one upload slot per frame.
type createSequenceResponse struct {
	TaskID  string       `json:"task_id"`
	Uploads []uploadSlot `json:"uploads"`
}

// parseFrame tells the parse API which uploaded object belongs to which frame.
type parseFrame struct {
	Index     int    `json:"index"`
	ObjectKey string `json:"object_key"`
}

// sequenceResult is the important part of the parse result.
// Feature vectors are usually 512-dimensional. face_feature may be empty when
// no usable face is found in the sequence.
// emotions is an optional SDK output, so the demo only prints its size when
// present.
type sequenceResult struct {
	SequenceID  string    `json:"sequence_id"`
	FrameCount  int       `json:"frame_count"`
	GaitFeature []float64 `json:"gait_feature"`
	ReIDFeature []float64 `json:"reid_feature"`
	FaceFeature []float64 `json:"face_feature"`
	Emotions    []int     `json:"emotions"`
}

func main() {
	client := &http.Client{Timeout: timeout}
	apiKey := registeredAPIKey()

	// Step 1: read all sequence frames from the local directory.
	seqDir := sequenceDir()
	frames, err := collectFrames(seqDir)
	must(err)
	if len(frames) == 0 {
		must(fmt.Errorf("no image frames under %s", seqDir))
	}

	// Step 2: create a sequence task. The server returns upload slots.
	var created createSequenceResponse
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences", map[string]any{"frame_count": len(frames)}, &created))
	if len(created.Uploads) != len(frames) {
		must(fmt.Errorf("upload count mismatch: api=%d local=%d", len(created.Uploads), len(frames)))
	}

	// Step 3: upload all frames once, then build the frames payload for parsing.
	must(uploadFramesBatch(client, created.TaskID, uploadTokenFromUploads(created.Uploads), frames))
	parseFrames := make([]parseFrame, 0, len(frames))
	for _, slot := range created.Uploads {
		parseFrames = append(parseFrames, parseFrame{Index: slot.Index, ObjectKey: slot.ObjectKey})
	}

	var parsed struct {
		TaskID        string           `json:"task_id"`
		Status        string           `json:"status"`
		SequenceCount int              `json:"sequence_count"`
		Sequences     []sequenceResult `json:"sequences"`
	}

	var result struct {
		TaskID        string           `json:"task_id"`
		Status        string           `json:"status"`
		SequenceCount int              `json:"sequence_count"`
		Sequences     []sequenceResult `json:"sequences"`
	}
	var first sequenceResult
	// Step 4: start synchronous gait sequence parsing. Registered users are billed
	// from their account balance by the server.
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences/"+created.TaskID+"/parse", map[string]any{"frames": parseFrames}, &parsed))

	// Step 5: fetch the stored result. This is useful if the caller wants to
	// retrieve the result again later by task_id.
	must(doJSON(client, apiKey, http.MethodGet, "/v1/sequences/"+created.TaskID+"/result", nil, &result))
	if len(result.Sequences) == 0 {
		panic("sequence result is empty")
	}
	first = result.Sequences[0]

	fmt.Printf("task_id=%s\n", created.TaskID)
	fmt.Printf("status=%s\n", parsed.Status)
	fmt.Printf("sequence_count=%d\n", parsed.SequenceCount)
	fmt.Printf("sequence_id=%s\n", first.SequenceID)
	fmt.Printf("frame_count=%d\n", first.FrameCount)
	fmt.Printf("gait_feature_dim=%d\n", len(first.GaitFeature))
	fmt.Printf("reid_feature_dim=%d\n", len(first.ReIDFeature))
	fmt.Printf("face_feature_dim=%d\n", len(first.FaceFeature))
	fmt.Printf("same_person_threshold=%.2f\n", samePersonThreshold)
}

// doJSON sends an authenticated JSON request to the registered-user API.
func doJSON(client *http.Client, apiKey string, method string, path string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequest(method, strings.TrimRight(baseURL(), "/")+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d %s %s\n%s", resp.StatusCode, method, path, string(data))
	}
	if out != nil && len(data) > 0 {
		return json.Unmarshal(data, out)
	}
	return nil
}

func registeredAPIKey() string {
	apiKey := strings.TrimSpace(defaultAPIKey)
	if apiKey == "" || apiKey == "gak_your_api_key" {
		must(fmt.Errorf("edit defaultAPIKey in sequence_demo/main.go before running this demo"))
	}
	return apiKey
}

func baseURL() string {
	return strings.TrimRight(defaultBaseURL, "/")
}

func sequenceDir() string {
	if len(os.Args) > 1 && strings.TrimSpace(os.Args[1]) != "" {
		return os.Args[1]
	}
	return defaultSeqDir
}

func uploadFramesBatch(client *http.Client, taskID string, uploadToken string, frames []string) error {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	if err := writer.WriteField("upload_token", uploadToken); err != nil {
		return err
	}
	for i, filename := range frames {
		file, err := os.Open(filename)
		if err != nil {
			return err
		}
		contentType := mime.TypeByExtension(strings.ToLower(filepath.Ext(filename)))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
		header := make(textproto.MIMEHeader)
		header.Set("Content-Disposition", fmt.Sprintf(`form-data; name="frames"; filename="%06d%s"`, i, strings.ToLower(filepath.Ext(filename))))
		header.Set("Content-Type", contentType)
		part, err := writer.CreatePart(header)
		if err != nil {
			file.Close()
			return err
		}
		if _, err := io.Copy(part, file); err != nil {
			file.Close()
			return err
		}
		file.Close()
		_ = contentType
	}
	if err := writer.Close(); err != nil {
		return err
	}
	path := "/v1/sequences/" + taskID + "/uploads/batch"
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(baseURL(), "/")+path, &body)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+registeredAPIKey())
	req.Header.Set("Content-Type", writer.FormDataContentType())
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d POST %s\n%s", resp.StatusCode, path, string(respBody))
	}
	return nil
}

func uploadTokenFromUploads(uploads []uploadSlot) string {
	if len(uploads) == 0 {
		must(fmt.Errorf("create response has no upload slots"))
	}
	parsed, err := url.Parse(uploads[0].UploadURL)
	must(err)
	token := parsed.Query().Get("token")
	if token == "" {
		must(fmt.Errorf("upload_url has no token"))
	}
	return token
}

// collectFrames returns image files in deterministic name order.
func collectFrames(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	allowed := map[string]bool{".jpg": true, ".jpeg": true, ".png": true, ".bmp": true, ".webp": true}
	var frames []string
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if allowed[ext] {
			frames = append(frames, filepath.Join(dir, entry.Name()))
		}
	}
	sort.Strings(frames)
	return frames, nil
}

func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
