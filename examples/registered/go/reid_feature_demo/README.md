# ReID Go Demo

This demo reads one cropped person image, calls `POST /v1/features/reid`, and prints the 512-dimensional ReID feature plus billing result.

Edit `apiKey` at the top of `main.go`, then run:

```bash
go run . /path/to/person.jpg
```
