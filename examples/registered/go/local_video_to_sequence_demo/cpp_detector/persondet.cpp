#include "persondet.h"

#include <algorithm>
#include <chrono>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

// Build switches live here so the inference behavior is controlled from this
// translation unit instead of CMake compile definitions.
#if defined(_OPENMP)
#define PERSONDET_USE_OPENMP 1
#if defined(_MSC_VER)
#define PERSONDET_OMP_PARALLEL_FOR __pragma(omp parallel for schedule(static))
#define PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2 __pragma(omp parallel for collapse(2) schedule(static))
#else
#define PERSONDET_OMP_PARALLEL_FOR _Pragma("omp parallel for schedule(static)")
#define PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2 _Pragma("omp parallel for collapse(2) schedule(static)")
#endif
#include <omp.h>
#else
#define PERSONDET_USE_OPENMP 0
#define PERSONDET_OMP_PARALLEL_FOR
#define PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2
#endif

#if defined(__AVX2__)
#include <immintrin.h>
#define PERSONDET_SIMD_AVX2 1
#define PERSONDET_SIMD_NEON 0
#elif defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
#define PERSONDET_SIMD_AVX2 0
#define PERSONDET_SIMD_NEON 1
#else
#define PERSONDET_SIMD_AVX2 0
#define PERSONDET_SIMD_NEON 0
#endif

#if defined(__FMA__) || (defined(_MSC_VER) && PERSONDET_SIMD_AVX2)
#define PERSONDET_USE_FMA 1
#else
#define PERSONDET_USE_FMA 0
#endif

namespace persondet {
namespace {

struct Tensor {
    int c = 0;
    int h = 0;
    int w = 0;
    std::vector<float> data;

    Tensor() = default;
    Tensor(int channels, int height, int width) : c(channels), h(height), w(width), data((size_t)channels * height * width) {}

    float& at(int ch, int y, int x) {
        return data[((size_t)y * w + x) * c + ch];
    }

    const float& at(int ch, int y, int x) const {
        return data[((size_t)y * w + x) * c + ch];
    }
};

struct Blob {
    std::vector<uint32_t> shape;
    std::vector<float> data;
    bool conv1x1_transposed = false;
};

struct Detection {
    float x1 = 0.0f;
    float y1 = 0.0f;
    float x2 = 0.0f;
    float y2 = 0.0f;
    float score = 0.0f;
};

struct DetectParams {
    float score_threshold = 0.35f;
    float nms_threshold = 0.50f;
    int topk = 1000;
};

float sigmoid(float x) {
    x = std::max(-50.0f, std::min(50.0f, x));
    return 1.0f / (1.0f + std::exp(-x));
}

constexpr int kSiluLutN = 4096;
constexpr float kSiluLutMin = -8.0f;
constexpr float kSiluLutMax = 8.0f;
constexpr float kSiluLutScale = kSiluLutN / (kSiluLutMax - kSiluLutMin);

const std::array<float, kSiluLutN + 1>& silu_lut() {
    static const std::array<float, kSiluLutN + 1> table = [] {
        std::array<float, kSiluLutN + 1> t{};
        for (int i = 0; i <= kSiluLutN; ++i) {
            const float x = kSiluLutMin + (kSiluLutMax - kSiluLutMin) * i / kSiluLutN;
            t[i] = x * sigmoid(x);
        }
        return t;
    }();
    return table;
}

inline float silu(float x) {
    if (x >= kSiluLutMax) {
        return x;
    }
    if (x <= kSiluLutMin) {
        return 0.0f;
    }
    const int i = (int)((x - kSiluLutMin) * kSiluLutScale + 0.5f);
    return silu_lut()[i];
}

float iou(const Detection& a, const Detection& b) {
    float x1 = std::max(a.x1, b.x1);
    float y1 = std::max(a.y1, b.y1);
    float x2 = std::min(a.x2, b.x2);
    float y2 = std::min(a.y2, b.y2);
    float iw = std::max(0.0f, x2 - x1);
    float ih = std::max(0.0f, y2 - y1);
    float inter = iw * ih;
    float area_a = std::max(0.0f, a.x2 - a.x1) * std::max(0.0f, a.y2 - a.y1);
    float area_b = std::max(0.0f, b.x2 - b.x1) * std::max(0.0f, b.y2 - b.y1);
    return inter / std::max(area_a + area_b - inter, 1e-6f);
}

std::vector<Detection> nms(std::vector<Detection> dets, float threshold, int topk) {
    std::sort(dets.begin(), dets.end(), [](const Detection& a, const Detection& b) { return a.score > b.score; });
    if ((int)dets.size() > topk) {
        dets.resize(topk);
    }
    std::vector<Detection> keep;
    std::vector<char> removed(dets.size(), 0);
    for (size_t i = 0; i < dets.size(); ++i) {
        if (removed[i]) {
            continue;
        }
        keep.push_back(dets[i]);
        for (size_t j = i + 1; j < dets.size(); ++j) {
            if (!removed[j] && iou(dets[i], dets[j]) > threshold) {
                removed[j] = 1;
            }
        }
    }
    return keep;
}

const Blob& blob(const std::map<std::string, Blob>& blobs, const std::string& name) {
    auto it = blobs.find(name);
    if (it == blobs.end()) {
        throw std::runtime_error("missing blob: " + name);
    }
    return it->second;
}

bool has_blob(const std::map<std::string, Blob>& blobs, const std::string& name) {
    return blobs.find(name) != blobs.end();
}

bool profiling_enabled() {
    static bool enabled = [] {
        const char* value = std::getenv("PERSONDET_PROFILE");
        return value && value[0] && value[0] != '0';
    }();
    return enabled;
}

struct ProfileScope {
    const char* name;
    std::chrono::high_resolution_clock::time_point start;

    explicit ProfileScope(const char* scope_name) : name(scope_name), start(std::chrono::high_resolution_clock::now()) {}

    ~ProfileScope() {
        if (!profiling_enabled()) {
            return;
        }
        auto end = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(end - start).count();
        std::fprintf(stderr, "[persondet] %-16s %.3f ms\n", name, ms);
    }
};

bool is_conv1x1_weight(const Blob& blob) {
    return blob.shape.size() == 4 && blob.shape[2] == 1 && blob.shape[3] == 1;
}

void transpose_conv1x1_weight(Blob& blob) {
    if (!is_conv1x1_weight(blob) || blob.conv1x1_transposed) {
        return;
    }
    int out_c = (int)blob.shape[0];
    int in_c = (int)blob.shape[1];
    std::vector<float> transposed((size_t)out_c * in_c);
    for (int oc = 0; oc < out_c; ++oc) {
        for (int ic = 0; ic < in_c; ++ic) {
            transposed[(size_t)ic * out_c + oc] = blob.data[(size_t)oc * in_c + ic];
        }
    }
    blob.data = std::move(transposed);
    blob.conv1x1_transposed = true;
}

void transpose_stem_reorg_weight(Blob& blob) {
    if (!is_conv1x1_weight(blob) || blob.conv1x1_transposed || blob.shape[0] != 16 || blob.shape[1] != 27) {
        return;
    }
    std::vector<float> transposed(16 * 27);
    for (int oc = 0; oc < 16; ++oc) {
        for (int ic = 0; ic < 27; ++ic) {
            transposed[ic * 16 + oc] = blob.data[oc * 27 + ic];
        }
    }
    blob.data = std::move(transposed);
    blob.conv1x1_transposed = true;
}

Tensor bgr_to_tensor(const unsigned char* bgr, int width, int height, int stride) {
    ProfileScope profile("bgr_to_tensor");
    Tensor out(3, height, width);
    PERSONDET_OMP_PARALLEL_FOR
    for (int y = 0; y < height; ++y) {
        const unsigned char* row = bgr + y * stride;
        float* dst = out.data.data() + (size_t)y * width * 3;
        for (int x = 0; x < width; ++x) {
            dst[x * 3 + 0] = row[x * 3 + 0];
            dst[x * 3 + 1] = row[x * 3 + 1];
            dst[x * 3 + 2] = row[x * 3 + 2];
        }
    }
    return out;
}

Tensor conv1x1(const Tensor& in, const Blob& weight, const Blob& bias, bool relu) {
    ProfileScope profile("conv1x1");
    int out_c = (int)weight.shape[0];
    Tensor out(out_c, in.h, in.w);
    const int hw = in.h * in.w;
    PERSONDET_OMP_PARALLEL_FOR
    for (int pos = 0; pos < hw; ++pos) {
        const float* src = in.data.data() + (size_t)pos * in.c;
        float* dst = out.data.data() + (size_t)pos * out_c;
        int oc = 0;
#if PERSONDET_SIMD_AVX2
        for (; oc + 8 <= out_c; oc += 8) {
            __m256 sum = _mm256_loadu_ps(bias.data.data() + oc);
            for (int ic = 0; ic < in.c; ++ic) {
                __m256 wv = _mm256_loadu_ps(weight.data.data() + (size_t)ic * out_c + oc);
                __m256 xv = _mm256_set1_ps(src[ic]);
#if PERSONDET_USE_FMA
                sum = _mm256_fmadd_ps(xv, wv, sum);
#else
                sum = _mm256_add_ps(sum, _mm256_mul_ps(xv, wv));
#endif
            }
            float tmp[8];
            _mm256_storeu_ps(tmp, sum);
            for (int lane = 0; lane < 8; ++lane) {
                dst[oc + lane] = relu ? silu(tmp[lane]) : tmp[lane];
            }
        }
#elif PERSONDET_SIMD_NEON
        for (; oc + 4 <= out_c; oc += 4) {
            float32x4_t sum = vld1q_f32(bias.data.data() + oc);
            for (int ic = 0; ic < in.c; ++ic) {
                float32x4_t wv = vld1q_f32(weight.data.data() + (size_t)ic * out_c + oc);
                sum = vmlaq_n_f32(sum, wv, src[ic]);
            }
            float tmp[4];
            vst1q_f32(tmp, sum);
            for (int lane = 0; lane < 4; ++lane) {
                dst[oc + lane] = relu ? silu(tmp[lane]) : tmp[lane];
            }
        }
#endif
        for (; oc < out_c; ++oc) {
            float sum = bias.data[oc];
            for (int ic = 0; ic < in.c; ++ic) {
                sum += src[ic] * weight.data[(size_t)ic * out_c + oc];
            }
            dst[oc] = relu ? silu(sum) : sum;
        }
    }
    return out;
}

Tensor conv1x1_single_thread(const Tensor& in, const Blob& weight, const Blob& bias, bool relu) {
    return conv1x1(in, weight, bias, relu);
}

Tensor depthwise3x3(const Tensor& in, const Blob& weight, const Blob& bias, int stride, bool relu) {
    ProfileScope profile("depthwise3x3");
    int out_h = (in.h + 2 - 3) / stride + 1;
    int out_w = (in.w + 2 - 3) / stride + 1;
    Tensor out(in.c, out_h, out_w);
    PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2
    for (int c = 0; c < in.c; ++c) {
        for (int oy = 0; oy < out_h; ++oy) {
            const float* w = weight.data.data() + (size_t)c * 9;
            for (int ox = 0; ox < out_w; ++ox) {
                int iy0 = oy * stride - 1;
                int ix0 = ox * stride - 1;
                float sum = bias.data[c];
                if (iy0 >= 0 && iy0 + 2 < in.h && ix0 >= 0 && ix0 + 2 < in.w) {
                    const float* r0 = in.data.data() + ((size_t)iy0 * in.w + ix0) * in.c + c;
                    const float* r1 = r0 + (size_t)in.w * in.c;
                    const float* r2 = r1 + (size_t)in.w * in.c;
                    sum += r0[0] * w[0] + r0[in.c] * w[1] + r0[in.c * 2] * w[2];
                    sum += r1[0] * w[3] + r1[in.c] * w[4] + r1[in.c * 2] * w[5];
                    sum += r2[0] * w[6] + r2[in.c] * w[7] + r2[in.c * 2] * w[8];
                } else {
                    for (int ky = 0; ky < 3; ++ky) {
                        int iy = iy0 + ky;
                        if (iy < 0 || iy >= in.h) {
                            continue;
                        }
                        for (int kx = 0; kx < 3; ++kx) {
                            int ix = ix0 + kx;
                            if (ix < 0 || ix >= in.w) {
                                continue;
                            }
                            sum += in.data[((size_t)iy * in.w + ix) * in.c + c] * w[ky * 3 + kx];
                        }
                    }
                }
                out.data[((size_t)oy * out_w + ox) * in.c + c] = relu ? silu(sum) : sum;
            }
        }
    }
    return out;
}

Tensor reorg_conv(const Tensor& in, const Blob& weight, const Blob& bias) {
    ProfileScope profile("reorg_conv");
    int out_h = (in.h + 1) / 2;
    int out_w = (in.w + 1) / 2;
    Tensor out((int)weight.shape[0], out_h, out_w);
    PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2
    for (int oc = 0; oc < out.c; ++oc) {
        for (int oy = 0; oy < out_h; ++oy) {
            const float* w = weight.data.data() + (size_t)oc * 27;
            for (int ox = 0; ox < out_w; ++ox) {
                float sum = bias.data[oc];
                int idx = 0;
                for (int ic = 0; ic < 3; ++ic) {
                    for (int ky = 0; ky < 3; ++ky) {
                        int iy = oy * 2 + ky - 1;
                        for (int kx = 0; kx < 3; ++kx, ++idx) {
                            int ix = ox * 2 + kx - 1;
                            if (iy >= 0 && iy < in.h && ix >= 0 && ix < in.w) {
                                sum += in.data[((size_t)iy * in.w + ix) * in.c + ic] * w[idx];
                            }
                        }
                    }
                }
                out.data[((size_t)oy * out_w + ox) * out.c + oc] = silu(sum);
            }
        }
    }
    return out;
}

Tensor reorg_conv_bgr(const unsigned char* bgr, int width, int height, int stride, const Blob& weight, const Blob& bias) {
    ProfileScope profile("reorg_conv_bgr");
    int out_h = (height + 1) / 2;
    int out_w = (width + 1) / 2;
    Tensor out((int)weight.shape[0], out_h, out_w);
    const int out_hw = out_h * out_w;
    if (out.c == 16) {
        PERSONDET_OMP_PARALLEL_FOR
        for (int pos = 0; pos < out_hw; ++pos) {
            int oy = pos / out_w;
            int ox = pos - oy * out_w;
            int iy0 = oy * 2 - 1;
            int ix0 = ox * 2 - 1;
            float* dst = out.data.data() + (size_t)pos * 16;
#if PERSONDET_SIMD_AVX2
            __m256 s0 = _mm256_loadu_ps(bias.data.data());
            __m256 s1 = _mm256_loadu_ps(bias.data.data() + 8);
#elif PERSONDET_SIMD_NEON
            float32x4_t s0 = vld1q_f32(bias.data.data());
            float32x4_t s1 = vld1q_f32(bias.data.data() + 4);
            float32x4_t s2 = vld1q_f32(bias.data.data() + 8);
            float32x4_t s3 = vld1q_f32(bias.data.data() + 12);
#else
            float sum[16];
            for (int oc = 0; oc < 16; ++oc) {
                sum[oc] = bias.data[oc];
            }
#endif

            int idx = 0;
            for (int ic = 0; ic < 3; ++ic) {
                for (int ky = 0; ky < 3; ++ky) {
                    int iy = iy0 + ky;
                    for (int kx = 0; kx < 3; ++kx, ++idx) {
                        int ix = ix0 + kx;
                        if (iy < 0 || iy >= height || ix < 0 || ix >= width) {
                            continue;
                        }
                        float px = (float)bgr[(size_t)iy * stride + ix * 3 + ic];
#if PERSONDET_SIMD_AVX2
                        __m256 pxv = _mm256_set1_ps(px);
                        const float* w = weight.data.data() + idx * 16;
#if PERSONDET_USE_FMA
                        s0 = _mm256_fmadd_ps(pxv, _mm256_loadu_ps(w), s0);
                        s1 = _mm256_fmadd_ps(pxv, _mm256_loadu_ps(w + 8), s1);
#else
                        s0 = _mm256_add_ps(s0, _mm256_mul_ps(pxv, _mm256_loadu_ps(w)));
                        s1 = _mm256_add_ps(s1, _mm256_mul_ps(pxv, _mm256_loadu_ps(w + 8)));
#endif
#elif PERSONDET_SIMD_NEON
                        const float* w = weight.data.data() + idx * 16;
                        s0 = vmlaq_n_f32(s0, vld1q_f32(w), px);
                        s1 = vmlaq_n_f32(s1, vld1q_f32(w + 4), px);
                        s2 = vmlaq_n_f32(s2, vld1q_f32(w + 8), px);
                        s3 = vmlaq_n_f32(s3, vld1q_f32(w + 12), px);
#else
                        for (int oc = 0; oc < 16; ++oc) {
                            sum[oc] += px * weight.data[(size_t)idx * 16 + oc];
                        }
#endif
                    }
                }
            }
#if PERSONDET_SIMD_AVX2
            float tmp0[8];
            float tmp1[8];
            _mm256_storeu_ps(tmp0, s0);
            _mm256_storeu_ps(tmp1, s1);
            for (int lane = 0; lane < 8; ++lane) {
                dst[lane] = silu(tmp0[lane]);
                dst[8 + lane] = silu(tmp1[lane]);
            }
#elif PERSONDET_SIMD_NEON
            float tmp[16];
            vst1q_f32(tmp, s0);
            vst1q_f32(tmp + 4, s1);
            vst1q_f32(tmp + 8, s2);
            vst1q_f32(tmp + 12, s3);
            for (int lane = 0; lane < 16; ++lane) {
                dst[lane] = silu(tmp[lane]);
            }
#else
            for (int oc = 0; oc < 16; ++oc) {
                dst[oc] = silu(sum[oc]);
            }
#endif
        }
        return out;
    }
    PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2
    for (int oc = 0; oc < out.c; ++oc) {
        for (int oy = 0; oy < out_h; ++oy) {
            const float* w = weight.data.data() + (size_t)oc * 27;
            for (int ox = 0; ox < out_w; ++ox) {
                int iy0 = oy * 2 - 1;
                int ix0 = ox * 2 - 1;
                float sum = bias.data[oc];
                if (iy0 >= 0 && iy0 + 2 < height && ix0 >= 0 && ix0 + 2 < width) {
                    const unsigned char* r0 = bgr + (size_t)iy0 * stride + ix0 * 3;
                    const unsigned char* r1 = r0 + stride;
                    const unsigned char* r2 = r1 + stride;
                    sum += (float)r0[0] * w[0] + (float)r0[3] * w[1] + (float)r0[6] * w[2];
                    sum += (float)r1[0] * w[3] + (float)r1[3] * w[4] + (float)r1[6] * w[5];
                    sum += (float)r2[0] * w[6] + (float)r2[3] * w[7] + (float)r2[6] * w[8];
                    sum += (float)r0[1] * w[9] + (float)r0[4] * w[10] + (float)r0[7] * w[11];
                    sum += (float)r1[1] * w[12] + (float)r1[4] * w[13] + (float)r1[7] * w[14];
                    sum += (float)r2[1] * w[15] + (float)r2[4] * w[16] + (float)r2[7] * w[17];
                    sum += (float)r0[2] * w[18] + (float)r0[5] * w[19] + (float)r0[8] * w[20];
                    sum += (float)r1[2] * w[21] + (float)r1[5] * w[22] + (float)r1[8] * w[23];
                    sum += (float)r2[2] * w[24] + (float)r2[5] * w[25] + (float)r2[8] * w[26];
                } else {
                    int idx = 0;
                    for (int ic = 0; ic < 3; ++ic) {
                        for (int ky = 0; ky < 3; ++ky) {
                            int iy = iy0 + ky;
                            for (int kx = 0; kx < 3; ++kx, ++idx) {
                                int ix = ix0 + kx;
                                if (iy >= 0 && iy < height && ix >= 0 && ix < width) {
                                    const unsigned char* px = bgr + (size_t)iy * stride + ix * 3;
                                    sum += (float)px[ic] * w[idx];
                                }
                            }
                        }
                    }
                }
                out.data[((size_t)oy * out_w + ox) * out.c + oc] = silu(sum);
            }
        }
    }
    return out;
}

Tensor dwblock(const Tensor& in, const std::map<std::string, Blob>& blobs, const std::string& name, int stride) {
    ProfileScope profile("dwblock_fused");
    const Blob& dw_w = blob(blobs, name + ".dw.w");
    const Blob& dw_b = blob(blobs, name + ".dw.b");
    const Blob& pw_w = blob(blobs, name + ".pw.w");
    const Blob& pw_b = blob(blobs, name + ".pw.b");
    int out_c = (int)pw_w.shape[0];
    int out_h = (in.h + 2 - 3) / stride + 1;
    int out_w = (in.w + 2 - 3) / stride + 1;
    Tensor out(out_c, out_h, out_w);

    PERSONDET_OMP_PARALLEL_FOR
    for (int pos = 0; pos < out_h * out_w; ++pos) {
        int oy = pos / out_w;
        int ox = pos - oy * out_w;
        int iy0 = oy * stride - 1;
        int ix0 = ox * stride - 1;
        float* dst = out.data.data() + (size_t)pos * out_c;
        for (int oc = 0; oc < out_c; ++oc) {
            dst[oc] = pw_b.data[oc];
        }

        for (int ic = 0; ic < in.c; ++ic) {
            const float* w = dw_w.data.data() + (size_t)ic * 9;
            float dw = dw_b.data[ic];
            if (iy0 >= 0 && iy0 + 2 < in.h && ix0 >= 0 && ix0 + 2 < in.w) {
                const float* r0 = in.data.data() + ((size_t)iy0 * in.w + ix0) * in.c + ic;
                const float* r1 = r0 + (size_t)in.w * in.c;
                const float* r2 = r1 + (size_t)in.w * in.c;
                dw += r0[0] * w[0] + r0[in.c] * w[1] + r0[in.c * 2] * w[2];
                dw += r1[0] * w[3] + r1[in.c] * w[4] + r1[in.c * 2] * w[5];
                dw += r2[0] * w[6] + r2[in.c] * w[7] + r2[in.c * 2] * w[8];
            } else {
                for (int ky = 0; ky < 3; ++ky) {
                    int iy = iy0 + ky;
                    if (iy < 0 || iy >= in.h) {
                        continue;
                    }
                    for (int kx = 0; kx < 3; ++kx) {
                        int ix = ix0 + kx;
                        if (ix < 0 || ix >= in.w) {
                            continue;
                        }
                        dw += in.data[((size_t)iy * in.w + ix) * in.c + ic] * w[ky * 3 + kx];
                    }
                }
            }
            dw = silu(dw);

            const float* pw = pw_w.data.data() + (size_t)ic * out_c;
            int oc = 0;
#if PERSONDET_SIMD_AVX2
            __m256 dw_v = _mm256_set1_ps(dw);
            for (; oc + 8 <= out_c; oc += 8) {
                __m256 sum = _mm256_loadu_ps(dst + oc);
                __m256 wv = _mm256_loadu_ps(pw + oc);
#if PERSONDET_USE_FMA
                sum = _mm256_fmadd_ps(dw_v, wv, sum);
#else
                sum = _mm256_add_ps(sum, _mm256_mul_ps(dw_v, wv));
#endif
                _mm256_storeu_ps(dst + oc, sum);
            }
#elif PERSONDET_SIMD_NEON
            for (; oc + 4 <= out_c; oc += 4) {
                float32x4_t sum = vld1q_f32(dst + oc);
                sum = vmlaq_n_f32(sum, vld1q_f32(pw + oc), dw);
                vst1q_f32(dst + oc, sum);
            }
#endif
            for (; oc < out_c; ++oc) {
                dst[oc] += dw * pw[oc];
            }
        }

        for (int oc = 0; oc < out_c; ++oc) {
            dst[oc] = silu(dst[oc]);
        }
    }
    return out;
}

Tensor dwblock_unfused(const Tensor& in, const std::map<std::string, Blob>& blobs, const std::string& name, int stride) {
    Tensor x = depthwise3x3(in, blob(blobs, name + ".dw.w"), blob(blobs, name + ".dw.b"), stride, true);
    return conv1x1(x, blob(blobs, name + ".pw.w"), blob(blobs, name + ".pw.b"), true);
}

Tensor dwblock_auto(const Tensor& in, const std::map<std::string, Blob>& blobs, const std::string& name, int stride) {
    static bool fuse = [] {
        const char* value = std::getenv("PERSONDET_FUSE_DWBLOCK");
        return !(value && value[0] == '0');
    }();
    if (fuse) {
        return dwblock(in, blobs, name, stride);
    }
    return dwblock_unfused(in, blobs, name, stride);
}

Tensor add_tensors(const Tensor& a, const Tensor& b) {
    ProfileScope profile("add_tensors");
    Tensor out(a.c, a.h, a.w);
    PERSONDET_OMP_PARALLEL_FOR
    for (size_t i = 0; i < out.data.size(); ++i) {
        out.data[i] = a.data[i] + b.data[i];
    }
    return out;
}

Tensor upsample_nearest(const Tensor& in, int out_h, int out_w) {
    ProfileScope profile("upsample");
    Tensor out(in.c, out_h, out_w);
    PERSONDET_OMP_PARALLEL_FOR_COLLAPSE2
    for (int y = 0; y < out_h; ++y) {
        for (int x = 0; x < out_w; ++x) {
            int iy = std::min(in.h - 1, y * in.h / out_h);
            int ix = std::min(in.w - 1, x * in.w / out_w);
            const float* src = in.data.data() + ((size_t)iy * in.w + ix) * in.c;
            float* dst = out.data.data() + ((size_t)y * out_w + x) * in.c;
            for (int c = 0; c < in.c; ++c) {
                dst[c] = src[c];
            }
        }
    }
    return out;
}

struct HeadOut {
    Tensor obj;
    Tensor box;
};

HeadOut head_forward(const Tensor& in, const std::map<std::string, Blob>& blobs, const std::string& name) {
    Tensor x = has_blob(blobs, name + "_stem.dw.w") ? dwblock_auto(in, blobs, name + "_stem", 1) : in;
    if (has_blob(blobs, name + "_extra.dw.w")) {
        x = dwblock_auto(x, blobs, name + "_extra", 1);
    }
    return {
        conv1x1_single_thread(x, blob(blobs, name + "_obj.w"), blob(blobs, name + "_obj.b"), false),
        conv1x1_single_thread(x, blob(blobs, name + "_box.w"), blob(blobs, name + "_box.b"), false),
    };
}

void debug_head_scores(const char* name, const HeadOut& out) {
    if (!std::getenv("PERSONDET_DEBUG")) {
        return;
    }
    float max_logit = -1e30f;
    int max_x = 0;
    int max_y = 0;
    for (int y = 0; y < out.obj.h; ++y) {
        for (int x = 0; x < out.obj.w; ++x) {
            float logit = out.obj.at(0, y, x);
            if (logit > max_logit) {
                max_logit = logit;
                max_x = x;
                max_y = y;
            }
        }
    }
    std::fprintf(stderr, "[persondet] %s max_score=%.6f logit=%.6f at=%d,%d size=%dx%d\n", name, sigmoid(max_logit), max_logit, max_x, max_y, out.obj.w, out.obj.h);
}

void decode_level(
    const HeadOut& out,
    int stride,
    int width,
    int height,
    const DetectParams& params,
    std::vector<Detection>& dets) {
    for (int y = 0; y < out.obj.h; ++y) {
        for (int x = 0; x < out.obj.w; ++x) {
            float score = sigmoid(out.obj.at(0, y, x));
            if (score < params.score_threshold) {
                continue;
            }
            float tx = out.box.at(0, y, x);
            float ty = out.box.at(1, y, x);
            float tw = std::max(-8.0f, std::min(8.0f, out.box.at(2, y, x)));
            float th = std::max(-8.0f, std::min(8.0f, out.box.at(3, y, x)));
            float bw = std::exp(tw) * stride;
            float bh = std::exp(th) * stride;
            float cx = (x + tx) * stride;
            float cy = (y + ty) * stride;
            Detection d;
            d.x1 = std::max(0.0f, std::min(cx - bw * 0.5f, (float)(width - 1)));
            d.y1 = std::max(0.0f, std::min(cy - bh * 0.5f, (float)(height - 1)));
            d.x2 = std::max(0.0f, std::min(cx + bw * 0.5f, (float)(width - 1)));
            d.y2 = std::max(0.0f, std::min(cy + bh * 0.5f, (float)(height - 1)));
            d.score = score;
            dets.push_back(d);
        }
    }
}

}  // namespace

struct Detector::Impl {
    std::map<std::string, Blob> blobs;
    float* result_buffer = nullptr;
    int result_buffer_count = 0;
};

Detector::Detector(float* result_buffer, int result_buffer_count) : impl_(new Impl()) {
#if PERSONDET_USE_OPENMP
    if (!std::getenv("OMP_NUM_THREADS")) {
        omp_set_num_threads(std::min(16, std::max(1, omp_get_num_procs() / 2)));
    }
#endif
    impl_->result_buffer = result_buffer;
    impl_->result_buffer_count = std::max(0, result_buffer_count);
    for (unsigned int i = 0; i < builtin::kWeightCount; ++i) {
        const builtin::WeightBlob& src = builtin::kWeights[i];
        Blob dst;
        dst.shape.assign(src.shape, src.shape + src.ndim);
        dst.data.assign(src.data, src.data + src.count);
        if (std::string(src.name) == "stem_reorg.w") {
            transpose_stem_reorg_weight(dst);
        } else {
            transpose_conv1x1_weight(dst);
        }
        impl_->blobs[src.name] = std::move(dst);
    }
}

Detector::~Detector() {
    delete impl_;
}

static std::vector<Detection> detect_tensor(
    Tensor x,
    const std::map<std::string, Blob>& b,
    int width,
    int height,
    const DetectParams& params) {
    x = dwblock_auto(x, b, "stem1", 2);
    x = dwblock_auto(x, b, "stem2", 2);
    Tensor p8 = dwblock_auto(x, b, "stage8_0", 1);
    if (has_blob(b, "stage8_1.dw.w")) {
        p8 = dwblock_auto(p8, b, "stage8_1", 1);
    }
    Tensor p16 = dwblock_auto(p8, b, "stage16_0", 2);
    if (has_blob(b, "stage16_1.dw.w")) {
        p16 = dwblock_auto(p16, b, "stage16_1", 1);
    }

    Tensor p32 = dwblock_auto(p16, b, "stage32_0", 2);
    if (has_blob(b, "stage32_1.dw.w")) {
        p32 = dwblock_auto(p32, b, "stage32_1", 1);
    }
    Tensor u16_lat = conv1x1(p16, blob(b, "lat16.w"), blob(b, "lat16.b"), true);
    Tensor u16 = add_tensors(u16_lat, upsample_nearest(p32, p16.h, p16.w));
    Tensor u8_lat = conv1x1(p8, blob(b, "lat8.w"), blob(b, "lat8.b"), true);
    Tensor u8 = add_tensors(u8_lat, upsample_nearest(u16, p8.h, p8.w));

    HeadOut h8 = head_forward(u8, b, "head8");
    HeadOut h16 = head_forward(u16, b, "head16");
    debug_head_scores("head8", h8);
    debug_head_scores("head16", h16);

    std::vector<Detection> dets;
    decode_level(h8, 8, width, height, params, dets);
    decode_level(h16, 16, width, height, params, dets);
    const bool use_head32 = has_blob(b, "head32_obj.w");
    if (use_head32) {
        HeadOut h32 = head_forward(p32, b, "head32");
        decode_level(h32, 32, width, height, params, dets);
    }
    if (std::getenv("PERSONDET_DEBUG")) {
        std::fprintf(stderr, "[persondet] decoded=%zu score_thresh=%.6f nms=%.3f topk=%d\n", dets.size(), params.score_threshold, params.nms_threshold, params.topk);
    }
    auto kept = nms(std::move(dets), params.nms_threshold, params.topk);
    if (std::getenv("PERSONDET_DEBUG")) {
        std::fprintf(stderr, "[persondet] kept=%zu\n", kept.size());
    }
    return kept;
}

int Detector::detect_bgr(
    const unsigned char* bgr,
    int width,
    int height,
    int stride,
    float score_threshold,
    float nms_threshold,
    int topk) {
    if (!bgr || width <= 0 || height <= 0 || stride < width * 3 || !impl_->result_buffer || impl_->result_buffer_count <= 0) {
        return 0;
    }

    DetectParams params;
    params.score_threshold = score_threshold;
    params.nms_threshold = nms_threshold;
    params.topk = topk;

    Tensor stem = reorg_conv_bgr(bgr, width, height, stride, blob(impl_->blobs, "stem_reorg.w"), blob(impl_->blobs, "stem_reorg.b"));
    std::vector<Detection> dets = detect_tensor(std::move(stem), impl_->blobs, width, height, params);
    int count = std::min((int)dets.size(), impl_->result_buffer_count);
    for (int i = 0; i < count; ++i) {
        const Detection& d = dets[i];
        int x1 = (int)std::round(d.x1);
        int y1 = (int)std::round(d.y1);
        int x2 = (int)std::round(d.x2);
        int y2 = (int)std::round(d.y2);
        x1 = std::max(0, std::min(width - 1, x1));
        y1 = std::max(0, std::min(height - 1, y1));
        x2 = std::max(0, std::min(width - 1, x2));
        y2 = std::max(0, std::min(height - 1, y2));

        float* r = impl_->result_buffer + (size_t)i * 5;
        r[0] = (float)x1;
        r[1] = (float)y1;
        r[2] = (float)std::max(0, x2 - x1);
        r[3] = (float)std::max(0, y2 - y1);
        r[4] = d.score;
    }
    return count;
}

}  // namespace persondet
