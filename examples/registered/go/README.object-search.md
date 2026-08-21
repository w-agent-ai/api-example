# Object Search Go API Key Demo

This package calls `POST /v1/object-search` with one local image and a text prompt.

1. Edit `object_search_demo/main.go` and set `defaultAPIKey`.
2. Run:

```bash
go run ./object_search_demo/main.go ./example.jpg "person"
```

The response contains matching image boxes and billing information.
