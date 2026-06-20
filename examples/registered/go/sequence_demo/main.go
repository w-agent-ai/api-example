package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"net/http"
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
	defaultAPIKey = ""

	// A sequence is a directory of cropped person images belonging to one track.
	defaultSeqDir = "../../../sample_sequences/ID_0001"
	timeout       = 10 * time.Minute

	// When comparing two parsed sequences, compute face/gait/ReID dot products
	// and fuse them with fusedIdentitySimilarity. Scores above this threshold
	// are usually likely to be the same person.
	samePersonThreshold = 0.7
)

// uploadSlot is returned by POST /v1/sequences.
// Each local image must be uploaded to the matching upload_url.
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

// gaitPoseResult is returned by POST /v1/sequences/{task_id}/gait-pose.
// It is billed separately from full gait sequence parsing and only returns pose data.
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

	// Step 1: read all sequence frames from the local directory.
	seqDir := sequenceDir()
	frames, err := collectFrames(seqDir)
	must(err)
	if len(frames) == 0 {
		must(fmt.Errorf("no image frames under %s", seqDir))
	}

	// Step 2: create a sequence task. The server returns pre-signed upload URLs.
	var created createSequenceResponse
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences", map[string]any{"frame_count": len(frames)}, &created))
	if len(created.Uploads) != len(frames) {
		must(fmt.Errorf("upload count mismatch: api=%d local=%d", len(created.Uploads), len(frames)))
	}

	// Step 3: upload every frame, then build the frames payload for parsing.
	parseFrames := make([]parseFrame, 0, len(frames))
	for i, frame := range frames {
		slot := created.Uploads[i]
		must(uploadFile(client, slot.UploadURL, frame))
		parseFrames = append(parseFrames, parseFrame{Index: slot.Index, ObjectKey: slot.ObjectKey})
	}

	var gaitPose struct {
		TaskID string         `json:"task_id"`
		Status string         `json:"status"`
		Result gaitPoseResult `json:"result"`
	}

	// Step 4: call the standalone Gait Pose API. This is a separate billable
	// operation from full gait sequence parsing and returns only pose outputs.
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences/"+created.TaskID+"/gait-pose", map[string]any{"frames": parseFrames}, &gaitPose))

	var parsed struct {
		TaskID        string           `json:"task_id"`
		Status        string           `json:"status"`
		SequenceCount int              `json:"sequence_count"`
		Sequences     []sequenceResult `json:"sequences"`
	}

	// Step 5: start synchronous gait sequence parsing. Registered users are billed
	// from their account balance by the server.
	must(doJSON(client, apiKey, http.MethodPost, "/v1/sequences/"+created.TaskID+"/parse", map[string]any{"frames": parseFrames}, &parsed))

	// Step 6: fetch the stored result. This is useful if the caller wants to
	// retrieve the result again later by task_id.
	var result struct {
		TaskID        string           `json:"task_id"`
		Status        string           `json:"status"`
		SequenceCount int              `json:"sequence_count"`
		Sequences     []sequenceResult `json:"sequences"`
	}
	must(doJSON(client, apiKey, http.MethodGet, "/v1/sequences/"+created.TaskID+"/result", nil, &result))
	if len(result.Sequences) == 0 {
		panic("sequence result is empty")
	}
	first := result.Sequences[0]

	fmt.Printf("task_id=%s\n", created.TaskID)
	fmt.Printf("status=%s\n", parsed.Status)
	fmt.Printf("sequence_count=%d\n", parsed.SequenceCount)
	fmt.Printf("sequence_id=%s\n", first.SequenceID)
	fmt.Printf("frame_count=%d\n", first.FrameCount)
	fmt.Printf("gait_feature_dim=%d\n", len(first.GaitFeature))
	fmt.Printf("reid_feature_dim=%d\n", len(first.ReIDFeature))
	fmt.Printf("face_feature_dim=%d\n", len(first.FaceFeature))
	fmt.Printf("same_person_threshold=%.2f\n", samePersonThreshold)
	fmt.Printf("gait_pose_status=%s\n", gaitPose.Status)
	fmt.Printf("gait_pose_pose2d_frames=%d\n", len(gaitPose.Result.Pose2Ds))
	fmt.Printf("gait_pose_pose3d_frames=%d\n", len(gaitPose.Result.Pose3Ds))
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
	apiKey := strings.TrimSpace(os.Getenv("GAIT_REGISTERED_API_KEY"))
	if apiKey == "" {
		apiKey = defaultAPIKey
	}
	if apiKey == "" {
		must(fmt.Errorf("export GAIT_REGISTERED_API_KEY before running this demo"))
	}
	return apiKey
}

func baseURL() string {
	value := strings.TrimSpace(os.Getenv("GAIT_API_BASE_URL"))
	if value == "" {
		value = defaultBaseURL
	}
	return value
}

func sequenceDir() string {
	value := strings.TrimSpace(os.Getenv("GAIT_SEQUENCE_DIR"))
	if value == "" {
		value = defaultSeqDir
	}
	return value
}

// uploadFile sends one frame to the upload_url returned by the create API.
// Upload URLs are service-relative paths in this deployment.
func uploadFile(client *http.Client, uploadPath string, filename string) error {
	data, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPut, strings.TrimRight(baseURL(), "/")+"/"+strings.TrimLeft(uploadPath, "/"), bytes.NewReader(data))
	if err != nil {
		return err
	}
	contentType := mime.TypeByExtension(strings.ToLower(filepath.Ext(filename)))
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	req.Header.Set("Content-Type", contentType)
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ = io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d PUT %s\n%s", resp.StatusCode, uploadPath, string(data))
	}
	return nil
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
