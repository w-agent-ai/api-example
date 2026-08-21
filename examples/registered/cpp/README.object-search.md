# Object Search C++ API Key Demo

This package sends one local image and a text prompt to `POST /v1/object-search`.

1. Edit `object_search_demo/main.cpp` and set `kAPIKey`.
2. Build:

```bash
cmake -S object_search_demo -B build
cmake --build build
```

3. Run:

```bash
./build/w_agent_object_search_demo ./example.jpg "person"
```

The response contains matching image boxes and billing information. The image is sent as raw Base64 without a `data:image/...` prefix.
