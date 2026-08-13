# C++ ReID API Demo

This package only demonstrates ReID feature extraction for registered users.

It reads one cropped person image and calls `POST /v1/features/reid` to get a 512-dimensional feature.

Edit `kAPIKey` in `reid_feature_demo/main.cpp` before building.
