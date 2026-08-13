# ReID C++ Demo

This demo shows the single-person-image-to-ReID-feature flow:

1. Read one cropped person image.
2. Call `POST /v1/features/reid`.
3. Print the 512-dimensional ReID feature and billing result.

Install dependencies:

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev
```

Edit `kAPIKey` at the top of `main.cpp`, then run:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/w_agent_reid_feature_demo /path/to/person.jpg
```

The input should be one person crop. If the original image contains multiple people, detect and crop the target person before calling this API.
