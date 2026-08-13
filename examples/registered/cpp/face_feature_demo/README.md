# Face Recognition C++ Demo

This demo shows the full local-image-to-face-feature flow:

1. Read one image.
2. Load `face_detect.onnx` with CPU ONNX Runtime.
3. Detect the best face and 5 landmarks.
4. Align and crop the face by eye landmarks.
5. Call `POST /v1/features/face` to get a 512-dimensional face feature.

Install dependencies:

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev
```

Edit `kAPIKey` at the top of `main.cpp`, then run:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/w_agent_face_feature_demo /path/to/image.jpg
```

The server expects an aligned face crop. Face detection and alignment happen locally in this demo.
