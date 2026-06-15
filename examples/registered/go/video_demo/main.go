package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	// Public API endpoint. Change this to your own deployment if needed.
	defaultBaseURL = "http://116.198.210.0:3005"

	// Registered-user API Key. It is sent as: Authorization: Bearer <api_key>.
	defaultAPIKey = ""

	// A video file is uploaded once, then parsed asynchronously by the server.
	defaultVideoPath = "../../../video/0000.avi"
	timeout          = 30 * time.Minute
	pollInterval     = 2 * time.Second
)

type createVideoResponse struct {
	TaskID    string `json:"task_id"`
	UploadURL string `json:"upload_url"`
}

type sequenceResult struct {
	SequenceID  string      `json:"sequence_id"`
	FrameCount  int         `json:"frame_count"`
	GaitFeature []float64   `json:"gait_feature"`
	ReIDFeature []float64   `json:"reid_feature"`
	FaceFeature []float64   `json:"face_feature"`
	Pose2Ds     [][]float64 `json:"pose_2ds"`
	Pose3Ds     [][]float64 `json:"pose_3ds"`
	Emotions    []int       `json:"emotions"`
}

type videoResult struct {
	Status              string           `json:"status"`
	SequenceCount       int              `json:"sequence_count"`
	TotalSequenceFrames int              `json:"total_sequence_frames"`
	Sequences           []sequenceResult `json:"sequences"`
}

func main() {
	client := &http.Client{Timeout: timeout}
	baseURL := apiBaseURL()
	apiKey := registeredAPIKey()

	// Step 1: create a video task with filename, content type and file size.
	// The server returns an upload_url for the video binary.
	stat, err := os.Stat(defaultVideoPath)
	must(err)
	filename := filepath.Base(defaultVideoPath)
	contentType := mime.TypeByExtension(strings.ToLower(filepath.Ext(filename)))
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	var created createVideoResponse
	must(doJSON(client, baseURL, apiKey, http.MethodPost, "/v1/videos", map[string]any{
		"filename":     filename,
		"content_type": contentType,
		"size_bytes":   stat.Size(),
	}, &created))

	// Step 2: upload the whole video file, then notify the server that upload is
	// complete. Registered video parsing is asynchronous.
	must(uploadFile(client, baseURL, created.UploadURL, defaultVideoPath))
	must(doJSON(client, baseURL, apiKey, http.MethodPost, "/v1/videos/"+created.TaskID+"/complete", map[string]any{}, nil))

	// Step 3: poll until the worker finishes parsing. HTTP 409 means the result
	// is not ready yet.
	var result videoResult
	deadline := time.Now().Add(timeout)
	for {
		code, err := doJSONAllow(client, baseURL, apiKey, http.MethodGet, "/v1/videos/"+created.TaskID+"/result", nil, &result, 409)
		must(err)
		if code == http.StatusOK {
			break
		}
		if time.Now().After(deadline) {
			must(fmt.Errorf("timed out waiting for video result: %s", created.TaskID))
		}
		time.Sleep(pollInterval)
	}

	fmt.Printf("video_task_id=%s\n", created.TaskID)
	fmt.Printf("video_status=%s\n", result.Status)
	fmt.Printf("sequence_count=%d\n", result.SequenceCount)
	fmt.Printf("total_sequence_frames=%d\n", result.TotalSequenceFrames)
	if len(result.Sequences) > 0 {
		first := result.Sequences[0]
		fmt.Printf("first_sequence_id=%s\n", first.SequenceID)
		fmt.Printf("first_gait_feature_dim=%d\n", len(first.GaitFeature))
		fmt.Printf("first_reid_feature_dim=%d\n", len(first.ReIDFeature))
		fmt.Printf("first_face_feature_dim=%d\n", len(first.FaceFeature))
		fmt.Printf("first_pose2d_frames=%d\n", len(first.Pose2Ds))
		fmt.Printf("first_pose3d_frames=%d\n", len(first.Pose3Ds))
		fmt.Printf("first_emotions=%d\n", len(first.Emotions))
	}
	if len(result.Sequences) >= 2 {
		sim := compareSequences(result.Sequences[0], result.Sequences[1])
		fmt.Printf("same_person_threshold=%.2f\n", samePersonThreshold)
		fmt.Printf("seq0_seq1_gait_similarity=%.6f\n", sim.Gait)
		fmt.Printf("seq0_seq1_reid_similarity=%.6f\n", sim.ReID)
		fmt.Printf("seq0_seq1_face_similarity=%.6f\n", sim.Face)
		fmt.Printf("seq0_seq1_fused_similarity=%.6f\n", sim.Fused)
		fmt.Printf("seq0_seq1_same_person_likely=%t\n", sim.Fused > samePersonThreshold)
	}
}

const samePersonThreshold = 0.7

type similarity struct {
	Gait  float64
	ReID  float64
	Face  float64
	Fused float64
}

func compareSequences(left, right sequenceResult) similarity {
	gait := dotProduct(left.GaitFeature, right.GaitFeature)
	reid := dotProduct(left.ReIDFeature, right.ReIDFeature)
	face := dotProduct(left.FaceFeature, right.FaceFeature)
	return similarity{Gait: gait, ReID: reid, Face: face, Fused: fusedIdentitySimilarity(face, gait, reid)}
}

func dotProduct(left, right []float64) float64 {
	used := len(left)
	if len(right) < used {
		used = len(right)
	}
	var score float64
	for i := 0; i < used; i++ {
		score += left[i] * right[i]
	}
	return score
}

func fusedIdentitySimilarity(faceSim, gaitSim, reidSim float64) float64 {
	result := math.Max(gaitSim, 0.1)
	if faceSim > 0.45 {
		result = math.Max(gaitSim, 0.7)
	} else if faceSim > 0.35 {
		result *= 1.1
	} else if faceSim > 0.4 {
		result *= 1.1
	} else if faceSim != 0 && faceSim < 0.1 {
		result *= 0.9
	}
	if reidSim > 0.8 {
		result *= 1.1
	}
	if faceSim > 0.5 {
		result *= 1.1
	}
	if faceSim > 0.6 {
		result *= 1.1
	}
	if result > 1 {
		return 1
	}
	return result
}

// doJSON sends an authenticated JSON request to the registered-user API.
func doJSON(client *http.Client, baseURL string, apiKey string, method string, path string, body any, out any) error {
	_, err := doJSONAllow(client, baseURL, apiKey, method, path, body, out)
	return err
}

func doJSONAllow(client *http.Client, baseURL string, apiKey string, method string, path string, body any, out any, allowedStatuses ...int) (int, error) {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return 0, err
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequest(method, strings.TrimRight(baseURL, "/")+path, reader)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 && !statusAllowed(resp.StatusCode, allowedStatuses) {
		return resp.StatusCode, fmt.Errorf("HTTP %d %s %s\n%s", resp.StatusCode, method, path, string(data))
	}
	if out != nil && len(data) > 0 && resp.StatusCode == http.StatusOK {
		return resp.StatusCode, json.Unmarshal(data, out)
	}
	return resp.StatusCode, nil
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

func apiBaseURL() string {
	baseURL := strings.TrimSpace(os.Getenv("GAIT_API_BASE_URL"))
	if baseURL == "" {
		baseURL = defaultBaseURL
	}
	return strings.TrimRight(baseURL, "/")
}

// uploadFile sends the video to the upload_url returned by the create API.
// Upload URLs are service-relative paths in this deployment.
func uploadFile(client *http.Client, baseURL string, uploadPath string, filename string) error {
	data, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPut, strings.TrimRight(baseURL, "/")+"/"+strings.TrimLeft(uploadPath, "/"), bytes.NewReader(data))
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
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d PUT %s\n%s", resp.StatusCode, uploadPath, string(body))
	}
	return nil
}

func statusAllowed(status int, allowed []int) bool {
	for _, item := range allowed {
		if status == item {
			return true
		}
	}
	return false
}

func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
