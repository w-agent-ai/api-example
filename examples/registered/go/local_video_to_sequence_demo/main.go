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
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// Change these values before building/running the demo.
const (
	baseURL       = "https://www.w-agent.cn/api"
	apiKey        = "gak_your_api_key"
	videoPath     = "input.mp4"
	detectorPath  = "cpp_detector/build/local_video_sequence_extractor"
	requestTimout = 10 * time.Minute
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

func main() {
	if apiKey == "" || apiKey == "gak_your_api_key" {
		must(fmt.Errorf("edit apiKey in local_video_to_sequence_demo/main.go before running this demo"))
	}

	input := videoPath
	if len(os.Args) > 1 {
		input = os.Args[1]
	}
	if input == "" || input == "input.mp4" {
		must(fmt.Errorf("edit videoPath in local_video_to_sequence_demo/main.go or pass a video path argument"))
	}

	must(runDetector(input))
	sequenceRoot := strings.TrimSuffix(filepath.Base(input), filepath.Ext(input)) + "_gait_sequences"
	seqDirs, err := collectSequenceDirs(sequenceRoot)
	must(err)
	if len(seqDirs) == 0 {
		must(fmt.Errorf("no sequence folders generated under %s", sequenceRoot))
	}

	client := &http.Client{Timeout: requestTimout}
	fmt.Printf("sequence_count=%d\n", len(seqDirs))
	for _, seqDir := range seqDirs {
		fmt.Printf("uploading_sequence=%s\n", seqDir)
		result, err := uploadAndRun(client, seqDir)
		must(err)
		encoded, _ := json.MarshalIndent(result, "", "  ")
		fmt.Println(string(encoded))
	}
}

func runDetector(input string) error {
	detector := detectorPath
	if _, err := os.Stat(detector); err != nil {
		return fmt.Errorf("detector executable not found: %s; build it with: cmake -S cpp_detector -B cpp_detector/build -DCMAKE_BUILD_TYPE=Release && cmake --build cpp_detector/build -j", detector)
	}
	cmd := exec.Command(detector, input)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func uploadAndRun(client *http.Client, seqDir string) (map[string]any, error) {
	frames, err := collectFrames(seqDir)
	if err != nil {
		return nil, err
	}
	if len(frames) == 0 {
		return nil, fmt.Errorf("no image frames under %s", seqDir)
	}

	var created createSequenceResponse
	if err := doJSON(client, http.MethodPost, "/v1/sequences", map[string]any{"frame_count": len(frames)}, &created); err != nil {
		return nil, err
	}
	if len(created.Uploads) != len(frames) {
		return nil, fmt.Errorf("upload count mismatch: api=%d local=%d", len(created.Uploads), len(frames))
	}

	if err := uploadFramesBatch(client, created.TaskID, uploadTokenFromUploads(created.Uploads), frames); err != nil {
		return nil, err
	}
	parseFrames := make([]parseFrame, 0, len(frames))
	for _, slot := range created.Uploads {
		parseFrames = append(parseFrames, parseFrame{Index: slot.Index, ObjectKey: slot.ObjectKey})
	}

	var result map[string]any
	if err := doJSON(client, http.MethodPost, "/v1/sequences/"+created.TaskID+"/parse", map[string]any{"frames": parseFrames}, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func collectSequenceDirs(root string) ([]string, error) {
	items, err := os.ReadDir(root)
	if err != nil {
		return nil, err
	}
	var dirs []string
	for _, item := range items {
		if item.IsDir() {
			dirs = append(dirs, filepath.Join(root, item.Name()))
		}
	}
	sort.Strings(dirs)
	return dirs, nil
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

func doJSON(client *http.Client, method string, path string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequest(method, strings.TrimRight(baseURL, "/")+path, reader)
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
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(baseURL, "/")+path, &body)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
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
