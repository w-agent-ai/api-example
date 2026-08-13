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
	// Change these values before building/running the demo.
	defaultBaseURL = "https://www.w-agent.cn/api"
	defaultAPIKey  = "gak_your_api_key"
	defaultSeqDir  = "./images"
	timeout        = 10 * time.Minute
)

type uploadSlot struct {
	Index     int    `json:"index"`
	ObjectKey string `json:"object_key"`
	UploadURL string `json:"upload_url"`
}

type createSequenceResponse struct {
	TaskID  string       `json:"task_id"`
	Uploads []uploadSlot `json:"uploads"`
}

type parseFrame struct {
	Index     int    `json:"index"`
	ObjectKey string `json:"object_key"`
}

type gaitPoseResult struct {
	SequenceID string      `json:"sequence_id"`
	FrameCount int         `json:"frame_count"`
	Pose2Ds    [][]float64 `json:"pose_2ds"`
	Pose3Ds    [][]float64 `json:"pose_3ds"`
	Emotions   []int       `json:"emotions"`
}

func main() {
	client := &http.Client{Timeout: timeout}
	apiKey := registeredAPIKey()
	seqDir := sequenceDir()
	frames, err := collectFrames(seqDir)
	must(err)
	if len(frames) == 0 {
		must(fmt.Errorf("no image frames under %s", seqDir))
	}

	var created createSequenceResponse
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences", map[string]any{"frame_count": len(frames)}, &created))
	if len(created.Uploads) != len(frames) {
		must(fmt.Errorf("upload count mismatch: api=%d local=%d", len(created.Uploads), len(frames)))
	}

	must(uploadFramesBatch(client, created.TaskID, uploadTokenFromUploads(created.Uploads), frames))
	parseFrames := make([]parseFrame, 0, len(frames))
	for _, slot := range created.Uploads {
		parseFrames = append(parseFrames, parseFrame{Index: slot.Index, ObjectKey: slot.ObjectKey})
	}

	var pose struct {
		TaskID string         `json:"task_id"`
		Status string         `json:"status"`
		Result gaitPoseResult `json:"result"`
	}
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences/"+created.TaskID+"/gait-pose", map[string]any{"frames": parseFrames}, &pose))

	fmt.Printf("task_id=%s\n", created.TaskID)
	fmt.Printf("status=%s\n", pose.Status)
	fmt.Printf("sequence_id=%s\n", pose.Result.SequenceID)
	fmt.Printf("frame_count=%d\n", pose.Result.FrameCount)
	fmt.Printf("pose2d_frames=%d\n", len(pose.Result.Pose2Ds))
	fmt.Printf("pose3d_frames=%d\n", len(pose.Result.Pose3Ds))
}

func registeredAPIKey() string {
	apiKey := strings.TrimSpace(defaultAPIKey)
	if apiKey == "" || apiKey == "gak_your_api_key" {
		must(fmt.Errorf("edit defaultAPIKey in gait_pose_demo/main.go before running this demo"))
	}
	return apiKey
}

func sequenceDir() string {
	if len(os.Args) > 1 && strings.TrimSpace(os.Args[1]) != "" {
		return os.Args[1]
	}
	return defaultSeqDir
}

func collectFrames(seqDir string) ([]string, error) {
	items, err := os.ReadDir(seqDir)
	if err != nil {
		return nil, err
	}
	var frames []string
	for _, item := range items {
		if item.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(item.Name()))
		if ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".bmp" || ext == ".webp" {
			frames = append(frames, filepath.Join(seqDir, item.Name()))
		}
	}
	sort.Strings(frames)
	return frames, nil
}

func doJSON(client *http.Client, apiKey string, method string, path string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequest(method, strings.TrimRight(defaultBaseURL, "/")+path, reader)
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
	}
	if err := writer.Close(); err != nil {
		return err
	}
	path := "/v1/sequences/" + taskID + "/uploads/batch"
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(defaultBaseURL, "/")+path, &body)
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

func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
