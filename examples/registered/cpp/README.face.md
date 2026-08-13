# C++ Face Recognition API Demo

This package only demonstrates face recognition for registered users.

It reads one local image, uses the included `face_detect.onnx` model with CPU ONNX Runtime to detect and align a face, then calls `POST /v1/features/face` to get a 512-dimensional feature.

Edit `kAPIKey` in `face_feature_demo/main.cpp` before building.
