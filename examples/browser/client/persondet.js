(function () {
  "use strict";

  const DEFAULT_CONFIG = {
    scoreThreshold: 0.35,
    nmsThreshold: 0.50,
    resizeWidth: 640,
    defaultJump: 3,
    fallbackFps: 25,
    fpsSampleFrames: 12,
    decodePlaybackRate: 1,
    maxAge: 25,
    minFrames: 20,
    maxFrames: 500,
    requireMoving: true,
    minBoxWidth: 64,
    minBoxHeight: 128,
    matchIou: 0.30,
    enlarge: 0.20,
    movingPairChangeThreshold: 0.70,
    movingScaleThreshold: 0.30,
    topk: 1000,
    jpegQuality: 0.88,
    onnxInputWidth: 640,
    onnxInputHeight: 352,
  };

  class Tensor {
    constructor(h, w, c, data) {
      this.h = h;
      this.w = w;
      this.c = c;
      this.data = data || new Float32Array(h * w * c);
    }
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function roundToMultiple(value, multiple) {
    return Math.max(multiple, Math.round(value / multiple) * multiple);
  }

  function sigmoid(x) {
    return 1 / (1 + Math.exp(-clamp(x, -50, 50)));
  }

  function silu(x) {
    if (x >= 8) return x;
    if (x <= -8) return 0;
    return x * sigmoid(x);
  }

  function iouBox(a, b) {
    const x1 = Math.max(a[0], b[0]);
    const y1 = Math.max(a[1], b[1]);
    const x2 = Math.min(a[2], b[2]);
    const y2 = Math.min(a[3], b[3]);
    const iw = Math.max(0, x2 - x1);
    const ih = Math.max(0, y2 - y1);
    const inter = iw * ih;
    const areaA = Math.max(0, a[2] - a[0]) * Math.max(0, a[3] - a[1]);
    const areaB = Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
    return inter / Math.max(areaA + areaB - inter, 1e-6);
  }

  function nms(dets, threshold, topk) {
    dets.sort((a, b) => b.score - a.score);
    if (dets.length > topk) dets = dets.slice(0, topk);
    const keep = [];
    const removed = new Uint8Array(dets.length);
    for (let i = 0; i < dets.length; i += 1) {
      if (removed[i]) continue;
      keep.push(dets[i]);
      for (let j = i + 1; j < dets.length; j += 1) {
        if (!removed[j] && iouBox(dets[i].bbox, dets[j].bbox) > threshold) {
          removed[j] = 1;
        }
      }
    }
    return keep;
  }

  function getWeight(weights, name) {
    const blob = weights[name];
    if (!blob) throw new Error("missing persondet weight: " + name);
    return blob;
  }

  function hasWeight(weights, name) {
    return Boolean(weights[name]);
  }

  class PersonDetectorJS {
    constructor(weights, config) {
      this.weights = weights;
      this.config = { ...DEFAULT_CONFIG, ...(config || {}) };
    }

    conv1x1(x, name, relu) {
      const weight = getWeight(this.weights, name + ".w");
      const bias = getWeight(this.weights, name + ".b");
      const outC = weight.shape[0];
      const inC = weight.shape[1];
      const out = new Tensor(x.h, x.w, outC);
      const src = x.data;
      const dst = out.data;
      const w = weight.data;
      const b = bias.data;
      const hw = x.h * x.w;
      for (let pos = 0; pos < hw; pos += 1) {
        const srcBase = pos * x.c;
        const dstBase = pos * outC;
        for (let oc = 0; oc < outC; oc += 1) {
          let sum = b[oc];
          const wBase = oc * inC;
          for (let ic = 0; ic < inC; ic += 1) {
            sum += src[srcBase + ic] * w[wBase + ic];
          }
          dst[dstBase + oc] = relu ? silu(sum) : sum;
        }
      }
      return out;
    }

    dwblock(x, name, stride) {
      const dwWeight = getWeight(this.weights, name + ".dw.w").data;
      const dwBias = getWeight(this.weights, name + ".dw.b").data;
      const pwWeight = getWeight(this.weights, name + ".pw.w");
      const pwBias = getWeight(this.weights, name + ".pw.b").data;
      const outC = pwWeight.shape[0];
      const inC = x.c;
      const outH = Math.floor((x.h + 2 - 3) / stride) + 1;
      const outW = Math.floor((x.w + 2 - 3) / stride) + 1;
      const out = new Tensor(outH, outW, outC);
      const src = x.data;
      const dst = out.data;
      const pw = pwWeight.data;
      for (let oy = 0; oy < outH; oy += 1) {
        for (let ox = 0; ox < outW; ox += 1) {
          const dstBase = (oy * outW + ox) * outC;
          for (let oc = 0; oc < outC; oc += 1) dst[dstBase + oc] = pwBias[oc];
          const iy0 = oy * stride - 1;
          const ix0 = ox * stride - 1;
          for (let ic = 0; ic < inC; ic += 1) {
            let dw = dwBias[ic];
            const wBase = ic * 9;
            for (let ky = 0; ky < 3; ky += 1) {
              const iy = iy0 + ky;
              if (iy < 0 || iy >= x.h) continue;
              for (let kx = 0; kx < 3; kx += 1) {
                const ix = ix0 + kx;
                if (ix < 0 || ix >= x.w) continue;
                dw += src[(iy * x.w + ix) * inC + ic] * dwWeight[wBase + ky * 3 + kx];
              }
            }
            dw = silu(dw);
            for (let oc = 0; oc < outC; oc += 1) {
              dst[dstBase + oc] += dw * pw[oc * inC + ic];
            }
          }
          for (let oc = 0; oc < outC; oc += 1) {
            dst[dstBase + oc] = silu(dst[dstBase + oc]);
          }
        }
      }
      return out;
    }

    reorgConvRGBA(imageData) {
      const weight = getWeight(this.weights, "stem_reorg.w").data;
      const bias = getWeight(this.weights, "stem_reorg.b").data;
      const width = imageData.width;
      const height = imageData.height;
      const rgba = imageData.data;
      const outH = Math.floor((height + 1) / 2);
      const outW = Math.floor((width + 1) / 2);
      const out = new Tensor(outH, outW, 16);
      const dst = out.data;
      for (let oy = 0; oy < outH; oy += 1) {
        for (let ox = 0; ox < outW; ox += 1) {
          const outBase = (oy * outW + ox) * 16;
          for (let oc = 0; oc < 16; oc += 1) {
            let sum = bias[oc];
            let idx = 0;
            for (let ic = 0; ic < 3; ic += 1) {
              for (let ky = 0; ky < 3; ky += 1) {
                const iy = oy * 2 + ky - 1;
                for (let kx = 0; kx < 3; kx += 1, idx += 1) {
                  const ix = ox * 2 + kx - 1;
                  if (iy < 0 || iy >= height || ix < 0 || ix >= width) continue;
                  const rgbaBase = (iy * width + ix) * 4;
                  const px = ic === 0 ? rgba[rgbaBase + 2] : (ic === 1 ? rgba[rgbaBase + 1] : rgba[rgbaBase]);
                  sum += px * weight[oc * 27 + idx];
                }
              }
            }
            dst[outBase + oc] = silu(sum);
          }
        }
      }
      return out;
    }

    upsampleNearest(x, outH, outW) {
      const out = new Tensor(outH, outW, x.c);
      for (let y = 0; y < outH; y += 1) {
        const iy = Math.min(x.h - 1, Math.floor(y * x.h / outH));
        for (let x0 = 0; x0 < outW; x0 += 1) {
          const ix = Math.min(x.w - 1, Math.floor(x0 * x.w / outW));
          const srcBase = (iy * x.w + ix) * x.c;
          const dstBase = (y * outW + x0) * x.c;
          for (let c = 0; c < x.c; c += 1) out.data[dstBase + c] = x.data[srcBase + c];
        }
      }
      return out;
    }

    add(a, b) {
      const out = new Tensor(a.h, a.w, a.c);
      for (let i = 0; i < out.data.length; i += 1) out.data[i] = a.data[i] + b.data[i];
      return out;
    }

    head(x, name) {
      let y = x;
      if (hasWeight(this.weights, name + "_stem.dw.w")) y = this.dwblock(y, name + "_stem", 1);
      if (hasWeight(this.weights, name + "_extra.dw.w")) y = this.dwblock(y, name + "_extra", 1);
      return {
        obj: this.conv1x1(y, name + "_obj", false),
        box: this.conv1x1(y, name + "_box", false),
      };
    }

    forward(imageData) {
      let x = this.reorgConvRGBA(imageData);
      x = this.dwblock(x, "stem1", 2);
      x = this.dwblock(x, "stem2", 2);
      let p8 = this.dwblock(x, "stage8_0", 1);
      if (hasWeight(this.weights, "stage8_1.dw.w")) p8 = this.dwblock(p8, "stage8_1", 1);
      let p16 = this.dwblock(p8, "stage16_0", 2);
      if (hasWeight(this.weights, "stage16_1.dw.w")) p16 = this.dwblock(p16, "stage16_1", 1);
      let p32 = this.dwblock(p16, "stage32_0", 2);
      if (hasWeight(this.weights, "stage32_1.dw.w")) p32 = this.dwblock(p32, "stage32_1", 1);
      const u16 = this.add(this.conv1x1(p16, "lat16", true), this.upsampleNearest(p32, p16.h, p16.w));
      const u8 = this.add(this.conv1x1(p8, "lat8", true), this.upsampleNearest(u16, p8.h, p8.w));
      const outputs = [{ head: this.head(u8, "head8"), stride: 8 }, { head: this.head(u16, "head16"), stride: 16 }];
      if (hasWeight(this.weights, "head32_obj.w")) outputs.push({ head: this.head(p32, "head32"), stride: 32 });
      return outputs;
    }

    decode(outputs, width, height) {
      const dets = [];
      for (const item of outputs) {
        const obj = item.head.obj;
        const box = item.head.box;
        const stride = item.stride;
        for (let y = 0; y < obj.h; y += 1) {
          for (let x = 0; x < obj.w; x += 1) {
            const score = sigmoid(obj.data[(y * obj.w + x) * obj.c]);
            if (score < this.config.scoreThreshold) continue;
            const base = (y * box.w + x) * box.c;
            const tx = box.data[base];
            const ty = box.data[base + 1];
            const tw = clamp(box.data[base + 2], -8, 8);
            const th = clamp(box.data[base + 3], -8, 8);
            const bw = Math.exp(tw) * stride;
            const bh = Math.exp(th) * stride;
            const cx = (x + tx) * stride;
            const cy = (y + ty) * stride;
            dets.push({
              bbox: [
                clamp(cx - bw * 0.5, 0, width - 1),
                clamp(cy - bh * 0.5, 0, height - 1),
                clamp(cx + bw * 0.5, 0, width - 1),
                clamp(cy + bh * 0.5, 0, height - 1),
              ],
              score,
            });
          }
        }
      }
      return nms(dets, this.config.nmsThreshold, this.config.topk);
    }

    detect(imageData, scaleX, scaleY) {
      const outputs = this.forward(imageData);
      return this.decode(outputs, imageData.width, imageData.height).map((det) => ({
        bbox: [det.bbox[0] * scaleX, det.bbox[1] * scaleY, det.bbox[2] * scaleX, det.bbox[3] * scaleY],
        score: det.score,
      }));
    }
  }

  class PersonDetectorWasm {
    constructor(module, config) {
      this.module = module;
      this.config = { ...DEFAULT_CONFIG, ...(config || {}) };
      this.maxResults = this.config.topk || 1000;
      this.handle = module._persondet_create(this.maxResults);
      if (!this.handle) throw new Error("persondet wasm create failed");
    }

    destroy() {
      if (this.handle) {
        this.module._persondet_destroy(this.handle);
        this.handle = 0;
      }
    }

    detect(imageData, scaleX, scaleY) {
      const byteCount = imageData.data.byteLength;
      const ptr = this.module._malloc(byteCount);
      if (!ptr) throw new Error("persondet wasm malloc failed");
      try {
        this.module.HEAPU8.set(imageData.data, ptr);
        const count = this.module._persondet_detect_rgba(
          this.handle,
          ptr,
          imageData.width,
          imageData.height,
          this.config.scoreThreshold,
          this.config.nmsThreshold,
          this.config.topk,
        );
        const resultPtr = this.module._persondet_results(this.handle);
        const base = resultPtr >> 2;
        const dets = [];
        for (let i = 0; i < count; i += 1) {
          const off = base + i * 5;
          const x = this.module.HEAPF32[off];
          const y = this.module.HEAPF32[off + 1];
          const w = this.module.HEAPF32[off + 2];
          const h = this.module.HEAPF32[off + 3];
          dets.push({
            bbox: [x * scaleX, y * scaleY, (x + w) * scaleX, (y + h) * scaleY],
            score: this.module.HEAPF32[off + 4],
          });
        }
        return dets;
      } finally {
        this.module._free(ptr);
      }
    }
  }

  function browserAssetBase() {
    if (globalThis.WAgentBrowserAssetBase) return globalThis.WAgentBrowserAssetBase;
    if (globalThis.location && globalThis.location.protocol === "file:") return "";
    return "/portal/browser-assets/";
  }

  function joinAssetURL(base, name) {
    if (!base) return name;
    return base.replace(/\/?$/, "/") + name;
  }

  let mp4boxModulePromise = null;

  async function loadMP4BoxModule() {
    if (!mp4boxModulePromise) {
      mp4boxModulePromise = import(joinAssetURL(browserAssetBase(), "mp4box.all.mjs"));
    }
    return mp4boxModulePromise;
  }

  function serializeCodecBox(box, MP4Box) {
    if (!box || typeof box.write !== "function" || !MP4Box || typeof MP4Box.DataStream !== "function") return null;
    const stream = new MP4Box.DataStream(undefined, 0, MP4Box.Endianness && MP4Box.Endianness.BIG_ENDIAN);
    box.write(stream);
    const data = new Uint8Array(stream.buffer);
    const headerSize = box.hdr_size || 8;
    if (data.length <= headerSize) return null;
    return data.slice(headerSize).buffer;
  }

  function sampleDescriptionForTrack(mp4file, trackID) {
    if (!mp4file || !mp4file.moov || !Array.isArray(mp4file.moov.traks)) return null;
    const trak = mp4file.moov.traks.find((item) => item && item.tkhd && item.tkhd.track_id === trackID);
    const entries = trak && trak.mdia && trak.mdia.minf && trak.mdia.minf.stbl && trak.mdia.minf.stbl.stsd && trak.mdia.minf.stbl.stsd.entries;
    return entries && entries[0] ? entries[0] : null;
  }

  function decoderDescriptionFromSampleEntry(entry, MP4Box) {
    if (!entry) return null;
    return serializeCodecBox(entry.avcC || entry.hvcC || entry.vpcC || entry.av1C, MP4Box);
  }

  function codecSupportedByWebCodecs(codec) {
    return /^avc[13]\./i.test(codec || "") || /^hvc1\.|^hev1\./i.test(codec || "") || /^vp0[89]\./i.test(codec || "") || /^av01\./i.test(codec || "");
  }

  function microseconds(value, timescale) {
    if (!Number.isFinite(value) || !Number.isFinite(timescale) || timescale <= 0) return 0;
    return Math.round(value * 1000000 / timescale);
  }

  async function demuxVideoSamples(file) {
    if (!globalThis.VideoDecoder || !globalThis.EncodedVideoChunk) throw new Error("WebCodecs unsupported");
    const MP4Box = await loadMP4BoxModule();
    if (!MP4Box || typeof MP4Box.createFile !== "function") throw new Error("mp4box unavailable");
    const buffer = await file.arrayBuffer();
    const mp4file = MP4Box.createFile();
    const samples = [];
    let selectedTrack = null;
    let readyError = null;
    mp4file.onReady = (info) => {
      selectedTrack = info && info.videoTracks && info.videoTracks[0] ? info.videoTracks[0] : null;
      if (!selectedTrack) {
        readyError = new Error("no video track");
        return;
      }
      if (!codecSupportedByWebCodecs(selectedTrack.codec)) {
        readyError = new Error("unsupported codec: " + (selectedTrack.codec || ""));
        return;
      }
      mp4file.setExtractionOptions(selectedTrack.id, null, { nbSamples: 1000 });
      mp4file.start();
    };
    mp4file.onSamples = (id, user, batch) => {
      if (selectedTrack && id === selectedTrack.id && Array.isArray(batch)) samples.push(...batch);
    };
    const mp4Buffer = buffer;
    mp4Buffer.fileStart = 0;
    mp4file.appendBuffer(mp4Buffer, true);
    if (readyError) throw readyError;
    if (!selectedTrack) throw new Error("no video track");
    mp4file.flush();
    if (!samples.length) throw new Error("no video samples");
    const entry = sampleDescriptionForTrack(mp4file, selectedTrack.id);
    const config = {
      codec: selectedTrack.codec,
      codedWidth: selectedTrack.video && selectedTrack.video.width || selectedTrack.track_width || 0,
      codedHeight: selectedTrack.video && selectedTrack.video.height || selectedTrack.track_height || 0,
      description: decoderDescriptionFromSampleEntry(entry, MP4Box),
    };
    if (!config.codedWidth || !config.codedHeight) {
      delete config.codedWidth;
      delete config.codedHeight;
    }
    if (!config.description) delete config.description;
    const support = typeof VideoDecoder.isConfigSupported === "function" ? await VideoDecoder.isConfigSupported(config) : { supported: true, config };
    if (!support || support.supported === false) throw new Error("WebCodecs codec not supported");
    return { config: support.config || config, samples, track: selectedTrack };
  }

  function resizeImageDataNearest(imageData, width, height) {
    const out = new ImageData(width, height);
    const src = imageData.data;
    const dst = out.data;
    for (let y = 0; y < height; y += 1) {
      const sy = Math.min(imageData.height - 1, Math.floor(y * imageData.height / height));
      for (let x = 0; x < width; x += 1) {
        const sx = Math.min(imageData.width - 1, Math.floor(x * imageData.width / width));
        const srcBase = (sy * imageData.width + sx) * 4;
        const dstBase = (y * width + x) * 4;
        dst[dstBase] = src[srcBase];
        dst[dstBase + 1] = src[srcBase + 1];
        dst[dstBase + 2] = src[srcBase + 2];
        dst[dstBase + 3] = src[srcBase + 3];
      }
    }
    return out;
  }

  function resizeImageData(imageData, width, height) {
    if (imageData.width === width && imageData.height === height) return imageData;
    try {
      const source = typeof OffscreenCanvas === "function" ? new OffscreenCanvas(imageData.width, imageData.height) : document.createElement("canvas");
      source.width = imageData.width;
      source.height = imageData.height;
      source.getContext("2d").putImageData(imageData, 0, 0);
      const target = typeof OffscreenCanvas === "function" ? new OffscreenCanvas(width, height) : document.createElement("canvas");
      target.width = width;
      target.height = height;
      const ctx = target.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(source, 0, 0, width, height);
      return ctx.getImageData(0, 0, width, height);
    } catch (_) {
      return resizeImageDataNearest(imageData, width, height);
    }
  }

  class PersonDetectorOnnx {
    constructor(session, config) {
      this.session = session;
      this.config = { ...DEFAULT_CONFIG, ...(config || {}) };
      this.inputWidth = this.config.onnxInputWidth || 640;
      this.inputHeight = this.config.onnxInputHeight || 352;
      this.inputName = session.inputNames && session.inputNames[0] ? session.inputNames[0] : "images";
      this.outputNames = session.outputNames && session.outputNames.length ? session.outputNames.slice() : ["p3", "p4", "p5"];
      this.inputBuffer = null;
    }

    async detect(imageData, scaleX, scaleY) {
      const sourceWidth = imageData.width;
      const sourceHeight = imageData.height;
      const inputImage = resizeImageData(imageData, this.inputWidth, this.inputHeight);
      const width = inputImage.width;
      const height = inputImage.height;
      const rgba = inputImage.data;
      const inputSize = 1 * 3 * height * width;
      if (!this.inputBuffer || this.inputBuffer.length !== inputSize) {
        this.inputBuffer = new Float32Array(inputSize);
      }
      const input = this.inputBuffer;
      const planeSize = height * width;
      for (let i = 0, p = 0; i < rgba.length; i += 4, p += 1) {
        input[p] = rgba[i + 2];
        input[planeSize + p] = rgba[i + 1];
        input[planeSize * 2 + p] = rgba[i];
      }
      const tensor = new globalThis.ort.Tensor("float32", input, [1, 3, height, width]);
      const outputs = await this.session.run({ [this.inputName]: tensor });
      const dets = [];
      const outputSpecs = [
        { name: "p3", fallbackIndex: 0, stride: 8 },
        { name: "p4", fallbackIndex: 1, stride: 16 },
        { name: "p5", fallbackIndex: 2, stride: 32 },
      ];
      for (const spec of outputSpecs) {
        const fallbackName = this.outputNames[spec.fallbackIndex];
        const output = outputs[spec.name] || outputs[fallbackName];
        if (!output || !output.data || !output.dims || output.dims.length !== 4) continue;
        this.decodeOutput(output.data, output.dims, spec.stride, width, height, dets);
      }
      const localScaleX = sourceWidth / width * scaleX;
      const localScaleY = sourceHeight / height * scaleY;
      return nms(dets, this.config.nmsThreshold, this.config.topk).map((det) => ({
        bbox: [det.bbox[0] * localScaleX, det.bbox[1] * localScaleY, det.bbox[2] * localScaleX, det.bbox[3] * localScaleY],
        score: det.score,
      }));
    }

    decodeOutput(data, dims, stride, width, height, dets) {
      const channels = dims[1];
      const h = dims[2];
      const w = dims[3];
      if (channels < 5) return;
      const hw = h * w;
      for (let y = 0; y < h; y += 1) {
        for (let x = 0; x < w; x += 1) {
          const pos = y * w + x;
          const score = sigmoid(data[4 * hw + pos]);
          if (score < this.config.scoreThreshold) continue;
          const tx = data[pos];
          const ty = data[hw + pos];
          const tw = clamp(data[2 * hw + pos], -8, 8);
          const th = clamp(data[3 * hw + pos], -8, 8);
          const bw = Math.exp(tw) * stride;
          const bh = Math.exp(th) * stride;
          const cx = (x + tx) * stride;
          const cy = (y + ty) * stride;
          dets.push({
            bbox: [
              clamp(cx - bw * 0.5, 0, width - 1),
              clamp(cy - bh * 0.5, 0, height - 1),
              clamp(cx + bw * 0.5, 0, width - 1),
              clamp(cy + bh * 0.5, 0, height - 1),
            ],
            score,
          });
        }
      }
    }
  }

  async function loadOnnxDetector(cfg, progress) {
    const runtime = globalThis.ort;
    if (!runtime || !runtime.InferenceSession || !runtime.Tensor) return null;
    const base = browserAssetBase();
    try {
      runtime.env.wasm.numThreads = 1;
      runtime.env.wasm.wasmPaths = base || "./";
      const session = await runtime.InferenceSession.create(joinAssetURL(base, "gait_detect.onnx"), {
        executionProviders: ["wasm"],
        graphOptimizationLevel: "all",
      });
      progress({ stage: "detector", backend: "onnxruntime_wasm" });
      return new PersonDetectorOnnx(session, cfg);
    } catch (error) {
      console.warn("[W-Agent] persondet onnxruntime unavailable, falling back to native wasm:", error);
      return null;
    }
  }

  async function loadWasmModule() {
    if (typeof createPersonDetWasmModule !== "function") return null;
    try {
      return await createPersonDetWasmModule();
    } catch (error) {
      console.warn("[W-Agent] persondet wasm unavailable, falling back to JS:", error);
      return null;
    }
  }

  async function createDetector(cfg, progress) {
    const onnxDetector = await loadOnnxDetector(cfg, progress);
    if (onnxDetector) return onnxDetector;
    const wasmModule = await loadWasmModule();
    if (wasmModule) {
      progress({ stage: "detector", backend: "wasm_simd" });
      return new PersonDetectorWasm(wasmModule, cfg);
    }
    const weights = window.WAgentPersonDetWeights && window.WAgentPersonDetWeights.load();
    if (!weights) throw new Error("persondet weights are not loaded");
    progress({ stage: "detector", backend: "js" });
    return new PersonDetectorJS(weights, cfg);
  }

  function chooseJump(videoFps, cfg) {
    const jump = Number.parseInt(cfg && cfg.defaultJump, 10);
    return Number.isFinite(jump) && jump > 0 ? jump : 3;
  }

  async function estimateVideoFps(video, cfg) {
    if (typeof video.requestVideoFrameCallback !== "function") return cfg.fallbackFps || 25;
    const samples = [];
    try {
      video.currentTime = 0;
      await video.play();
      let previous = null;
      const target = Math.max(4, cfg.fpsSampleFrames || 12);
      const started = performance.now();
      while (samples.length < target && performance.now() - started < 1200 && !video.ended) {
        const metadata = await nextVideoFrame(video, 800);
        const mediaTime = Number.isFinite(metadata.mediaTime) ? metadata.mediaTime : video.currentTime;
        if (previous !== null && mediaTime > previous) samples.push(mediaTime - previous);
        previous = mediaTime;
      }
    } catch (_) {
      return cfg.fallbackFps || 25;
    } finally {
      video.pause();
    }
    const valid = samples.filter((item) => item > 0 && item < 1);
    if (!valid.length) return cfg.fallbackFps || 25;
    valid.sort((a, b) => a - b);
    const median = valid[Math.floor(valid.length / 2)];
    return Math.max(1, Math.min(120, 1 / median));
  }

  function rectInter(a, b) {
    const x1 = Math.max(a[0], b[0]);
    const y1 = Math.max(a[1], b[1]);
    const x2 = Math.min(a[0] + a[2], b[0] + b[2]);
    const y2 = Math.min(a[1] + a[3], b[1] + b[3]);
    return [x1, y1, Math.max(0, x2 - x1), Math.max(0, y2 - y1)];
  }

  function isSequenceMoving(width, height, rects, cfg) {
    if (!rects.length) return false;
    const valid = rects.filter((r) => r[2] > 0 && r[3] > 0);
    if (!valid.length) return false;
    let common = valid[0].slice();
    for (const r1 of valid) {
      common = rectInter(common, r1);
      for (const r2 of valid) {
        const inter = rectInter(r1, r2);
        const change = 1 - Math.min(
          inter[2] * inter[3] / Math.max(1, r1[2] * r1[3]),
          inter[2] * inter[3] / Math.max(1, r2[2] * r2[3]),
        );
        if (change > cfg.movingPairChangeThreshold) return true;
      }
    }
    const avgW = valid.reduce((s, r) => s + r[2], 0) / valid.length;
    const avgH = valid.reduce((s, r) => s + r[3], 0) / valid.length;
    if (common[2] < avgW * cfg.movingScaleThreshold || common[3] < avgH * cfg.movingScaleThreshold) return true;
    const centersX = valid.map((r) => r[0] + r[2] / 2);
    const centersY = valid.map((r) => r[1] + r[3] / 2);
    const scaleX = (Math.max(...centersX) - Math.min(...centersX)) / Math.max(avgW, 1);
    const scaleY = (Math.max(...centersY) - Math.min(...centersY)) / Math.max(avgH, 1);
    if (scaleY < 0.1) {
      const topY = Math.min(...valid.map((r) => r[1]));
      const bottomY = Math.max(...valid.map((r) => r[1] + r[3]));
      const tap = height / 20;
      if (topY > tap && bottomY < height - tap) return false;
    }
    return !(scaleX < cfg.movingScaleThreshold && scaleY < cfg.movingScaleThreshold);
  }

  function enlargeBox(box, ratio, width, height) {
    let [x1, y1, x2, y2] = box;
    const bw = x2 - x1;
    const bh = y2 - y1;
    x1 = Math.max(0, Math.floor(x1 - bw * ratio * 0.5));
    y1 = Math.max(0, Math.floor(y1 - bh * ratio * 0.5));
    x2 = Math.min(width, Math.ceil(x2 + bw * ratio * 0.5));
    y2 = Math.min(height, Math.ceil(y2 + bh * ratio * 0.5));
    return [x1, y1, Math.max(0, x2 - x1), Math.max(0, y2 - y1)];
  }

  function canvasBlob(canvas, quality) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("canvas export failed")), "image/jpeg", quality);
    });
  }

  async function cropToBlob(sourceCanvas, crop, cfg) {
    const [x, y, w, h] = crop;
    const out = document.createElement("canvas");
    out.width = w;
    out.height = h;
    out.getContext("2d").drawImage(sourceCanvas, x, y, w, h, 0, 0, w, h);
    return canvasBlob(out, cfg.jpegQuality);
  }

  async function exportSequence(seq, cfg) {
    const keepFrames = seq.frames;
    const frames = [];
    for (let i = 0; i < keepFrames.length; i += 1) {
      const item = keepFrames[i];
      frames.push({
        index: i,
        frame_id: item.frame_id,
        time: item.time,
        content_base64: item.content_base64,
        image_base64: item.image_base64,
        base64: item.base64,
        content_blob: item.content_blob,
        preview_base64: item.preview_base64,
        cacheFile: item.cacheFile,
        cacheHandle: item.cacheHandle,
      });
    }
    const firstFrame = keepFrames[0] || {};
    const lastFrame = keepFrames[keepFrames.length - 1] || firstFrame;
    return {
      sequence_id: seq.seq_id,
      track_id: seq.track_id,
      source_frames: seq.frames.length,
      uploaded_frames: frames.length,
      start_frame: firstFrame.frame_id || 0,
      end_frame: lastFrame.frame_id || 0,
      start_time: Number.isFinite(firstFrame.time) ? firstFrame.time : 0,
      end_time: Number.isFinite(lastFrame.time) ? lastFrame.time : 0,
      frames,
      boxes: keepFrames.map((item) => ({
        x1: item.det[0],
        y1: item.det[1],
        x2: item.det[0] + item.det[2],
        y2: item.det[1] + item.det[3],
        label: "seq " + seq.seq_id + " / frame " + item.frame_id,
      })),
    };
  }

  function seekVideo(video, time) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("视频 seek 超时。")), 8000);
      video.onseeked = () => {
        clearTimeout(timeout);
        resolve();
      };
      video.onerror = () => {
        clearTimeout(timeout);
        reject(new Error("视频解码失败，浏览器不支持该格式。"));
      };
      if (Math.abs(video.currentTime - time) < 0.001) {
        clearTimeout(timeout);
        resolve();
        return;
      }
      video.currentTime = time;
    });
  }

  function nextVideoFrame(video, timeoutMs) {
    return new Promise((resolve, reject) => {
      if (typeof video.requestVideoFrameCallback !== "function") {
        reject(new Error("requestVideoFrameCallback unsupported"));
        return;
      }
      let done = false;
      let timeout = 0;
      const finish = (fn, value) => {
        if (done) return;
        done = true;
        if (timeout) clearTimeout(timeout);
        fn(value);
      };
      const callbackID = video.requestVideoFrameCallback((_, metadata) => finish(resolve, metadata || {}));
      if (timeoutMs > 0) {
        timeout = setTimeout(() => {
          if (typeof video.cancelVideoFrameCallback === "function") video.cancelVideoFrameCallback(callbackID);
          finish(reject, new Error("video frame callback timed out"));
        }, timeoutMs);
      }
      video.onerror = () => {
        if (typeof video.cancelVideoFrameCallback === "function") video.cancelVideoFrameCallback(callbackID);
        finish(reject, new Error("视频解码失败，浏览器不支持该格式。"));
      };
    });
  }

  function isVideoFrameTimeout(error) {
    return /video frame callback timed out/i.test(error && error.message || "");
  }

  async function extractLocalVideoSequence(file, options) {
    const cfg = { ...DEFAULT_CONFIG, ...((options && options.config) || {}) };
    const progress = options && options.progress ? options.progress : function () {};
    const onSequence = options && options.onSequence ? options.onSequence : null;
    const onFrame = options && options.onFrame ? options.onFrame : null;
    const onDiscard = options && options.onDiscard ? options.onDiscard : null;
    const signal = options && options.signal;
    let detectorBackend = "";
    let decodeMode = "";
    let detector = null;
    let video = null;
    let cleanedUp = false;
    const cleanup = () => {
      if (cleanedUp) return;
      cleanedUp = true;
      if (video) {
        video.pause();
        URL.revokeObjectURL(video.src);
      }
      if (detector && detector.destroy) detector.destroy();
    };
    const abortError = () => {
      try {
        return new DOMException("视频解析已停止。", "AbortError");
      } catch (_) {
        const error = new Error("视频解析已停止。");
        error.name = "AbortError";
        return error;
      }
    };
    const checkAborted = () => {
      if (signal && signal.aborted) throw abortError();
    };
    const reportProgress = (event) => {
      if (event && event.stage === "detector") detectorBackend = event.backend || "";
      if (event && event.stage === "decode") {
        decodeMode = event.mode || "";
        if (decodeMode) console.info("[W-Agent] decode mode:", decodeMode, "video:", file && file.name ? file.name : "(unknown)");
      }
      progress(event);
    };
    checkAborted();
    reportProgress({ stage: "detector_loading" });
    detector = await createDetector(cfg, reportProgress);
    try {
      checkAborted();
    } catch (error) {
      cleanup();
      throw error;
    }
    video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.src = URL.createObjectURL(file);
    try {
      checkAborted();
      reportProgress({ stage: "metadata_loading" });
      await new Promise((resolve, reject) => {
        video.onloadedmetadata = resolve;
        video.onerror = () => reject(new Error("视频解码失败，浏览器不支持该格式。"));
      });
      checkAborted();
    } catch (error) {
      cleanup();
      throw error;
    }
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    reportProgress({ stage: "fps_sampling" });
    const fps = await estimateVideoFps(video, cfg);
    const jump = chooseJump(fps, cfg);
    const step = jump / fps;
    reportProgress({ stage: "sampling", fps, jump, effective_fps: fps / jump });
    const rawW = video.videoWidth;
    const rawH = video.videoHeight;
    let detW = rawW;
    let detH = rawH;
    if (detector && detector.inputWidth > 0 && detector.inputHeight > 0) {
      detW = detector.inputWidth;
      detH = detector.inputHeight;
    } else if (cfg.resizeWidth > 0 && Math.max(rawW, rawH) > cfg.resizeWidth) {
      if (rawW >= rawH) {
        detW = cfg.resizeWidth;
        detH = roundToMultiple(rawH * detW / rawW, 32);
      } else {
        detH = cfg.resizeWidth;
        detW = roundToMultiple(rawW * detH / rawH, 32);
      }
    }
    const detCanvas = document.createElement("canvas");
    detCanvas.width = detW;
    detCanvas.height = detH;
    const detCtx = detCanvas.getContext("2d", { willReadFrequently: true });
    const fullCanvas = document.createElement("canvas");
    fullCanvas.width = rawW;
    fullCanvas.height = rawH;
    const fullCtx = fullCanvas.getContext("2d");
    const scaleX = rawW / detW;
    const scaleY = rawH / detH;
    const tracks = [];
    const seqs = new Map();
    let nextTrackID = 1;
    let nextSeqID = 1;
    let processed = 0;
    let rejectedShort = 0;
    let rejectedStatic = 0;
    const timings = { seek_ms: 0, draw_ms: 0, detect_ms: 0, crop_ms: 0, track_ms: 0 };

    async function emitSequence(seq) {
      let exported = await exportSequence(seq, cfg);
      if (onSequence) {
        const handled = await onSequence(exported, completed.length + 1);
        if (handled) exported = handled;
      }
      reportProgress({ stage: "sequence_ready", current: completed.length + 1, sequence: exported });
      return exported;
    }

    async function appendFrame(seq, frameID, det) {
      const [x1, y1, x2, y2] = det.box;
      const detRect = [Math.round(x1), Math.round(y1), Math.round(x2 - x1), Math.round(y2 - y1)];
      const crop = enlargeBox(det.box, cfg.enlarge, rawW, rawH);
      if (crop[2] <= 0 || crop[3] <= 0) return;
      const cropStart = performance.now();
      const contentBlob = await cropToBlob(fullCanvas, crop, cfg);
      timings.crop_ms += performance.now() - cropStart;
      const frame = { frame_id: frameID, time: duration > 0 ? Math.max(0, Math.min(duration, (frameID - 1) / fps)) : 0, score: det.score, det: detRect, crop, content_blob: contentBlob };
      seq.frames.push(frame);
      if (onFrame) await onFrame(seq, frame, seq.frames.length - 1);
    }

    async function finishTrack(track, options) {
      const force = options && options.force;
      const seq = seqs.get(track.seqID);
      if (!seq) return null;
      seqs.delete(track.seqID);
      if (seq.frames.length < cfg.minFrames) {
        rejectedShort += 1;
        if (onDiscard) await onDiscard(seq, "short");
        return null;
      }
      if (!force && cfg.requireMoving !== false && !isSequenceMoving(rawW, rawH, seq.frames.map((f) => f.det), cfg)) {
        rejectedStatic += 1;
        if (onDiscard) await onDiscard(seq, "static");
        return null;
      }
      const exported = await emitSequence(seq);
      completed.push(exported);
      return exported;
    }

    const completed = [];
    let totalFramesEstimate = duration > 0 ? Math.ceil(duration * fps) : 0;

    function resetExtractionState() {
      tracks.length = 0;
      seqs.clear();
      completed.length = 0;
      nextTrackID = 1;
      nextSeqID = 1;
      processed = 0;
      rejectedShort = 0;
      rejectedStatic = 0;
    }

    async function processCurrentFrame(frameID, source) {
      checkAborted();
      const drawSource = source || video;
      const drawStart = performance.now();
      fullCtx.drawImage(drawSource, 0, 0, rawW, rawH);
      detCtx.drawImage(drawSource, 0, 0, detW, detH);
      const imageData = detCtx.getImageData(0, 0, detW, detH);
      timings.draw_ms += performance.now() - drawStart;
      const detectStart = performance.now();
      const dets = (await detector.detect(imageData, scaleX, scaleY))
        .map((det) => ({ box: det.bbox, score: det.score }))
        .filter((det) => det.box[2] - det.box[0] >= cfg.minBoxWidth && det.box[3] - det.box[1] >= cfg.minBoxHeight);
      timings.detect_ms += performance.now() - detectStart;

      const trackStart = performance.now();
      const matchedTracks = new Set();
      const matchedDets = new Set();
      const pairs = [];
      for (let ti = 0; ti < tracks.length; ti += 1) {
        for (let di = 0; di < dets.length; di += 1) {
          const iou = iouBox(tracks[ti].box, dets[di].box);
          if (iou >= cfg.matchIou) pairs.push([iou, ti, di]);
        }
      }
      pairs.sort((a, b) => b[0] - a[0]);
      for (const [, ti, di] of pairs) {
        if (matchedTracks.has(ti) || matchedDets.has(di)) continue;
        matchedTracks.add(ti);
        matchedDets.add(di);
        tracks[ti].box = dets[di].box;
        tracks[ti].missed = 0;
        await appendFrame(seqs.get(tracks[ti].seqID), frameID, dets[di]);
      }
      for (let ti = 0; ti < tracks.length; ti += 1) {
        if (!matchedTracks.has(ti)) tracks[ti].missed += 1;
      }
      for (let di = 0; di < dets.length; di += 1) {
        if (matchedDets.has(di)) continue;
        const seqID = nextSeqID++;
        const track = { trackID: nextTrackID++, seqID, box: dets[di].box, missed: 0 };
        tracks.push(track);
        const seq = { seq_id: seqID, track_id: track.trackID, frame_size: [rawW, rawH], frames: [] };
        seqs.set(seqID, seq);
        await appendFrame(seq, frameID, dets[di]);
      }
      for (let i = tracks.length - 1; i >= 0; i -= 1) {
        const seq = seqs.get(tracks[i].seqID);
        if (cfg.maxFrames > 0 && seq && seq.frames.length >= cfg.maxFrames) {
          const [track] = tracks.splice(i, 1);
          await finishTrack(track);
          continue;
        }
        if (tracks[i].missed > cfg.maxAge) {
          const [track] = tracks.splice(i, 1);
          await finishTrack(track);
        }
      }
      timings.track_ms += performance.now() - trackStart;
      processed += 1;
      if (processed % 5 === 0) {
        reportProgress({ processed, total: totalFramesEstimate, current_frame: frameID, activeTracks: tracks.length, detections: dets.length, timings });
        checkAborted();
        await new Promise((resolve) => setTimeout(resolve, 0));
        checkAborted();
      }
      return dets.length;
    }

    async function processWithWebCodecsDecode() {
      let demuxed;
      try {
        reportProgress({ stage: "decode_prepare", mode: "webcodecs" });
        demuxed = await demuxVideoSamples(file);
      } catch (error) {
        console.warn("[W-Agent] WebCodecs decode unavailable, falling back to video element:", error);
        return false;
      }
      reportProgress({ stage: "decode", mode: "webcodecs" });
      const samples = demuxed.samples || [];
      const track = demuxed.track || {};
      const trackTimescale = track.timescale || (samples[0] && samples[0].timescale) || fps;
      totalFramesEstimate = Math.max(totalFramesEstimate, samples.length);
      let decodedIndex = 0;
      let outputChain = Promise.resolve();
      let decodeError = null;
      let pendingOutputs = 0;
      const outputWaiters = [];
      const notifyOutputDrained = () => {
        while (outputWaiters.length && pendingOutputs < 3) outputWaiters.shift()();
      };
      const waitForOutputBacklog = () => {
        if (pendingOutputs < 3) return Promise.resolve();
        return new Promise((resolve) => outputWaiters.push(resolve));
      };
      const waitForDecoderQueue = (decoder, maxSize) => {
        if (!decoder || decoder.decodeQueueSize < maxSize) return Promise.resolve();
        return new Promise((resolve) => {
          const done = () => {
            clearTimeout(timer);
            decoder.removeEventListener("dequeue", done);
            resolve();
          };
          const timer = setTimeout(done, 1000);
          decoder.addEventListener("dequeue", done, { once: true });
        });
      };
      const decoder = new VideoDecoder({
        output: (frame) => {
          const frameIndex = decodedIndex;
          decodedIndex += 1;
          pendingOutputs += 1;
          outputChain = outputChain.then(async () => {
            try {
              if (frameIndex % jump === 0) {
                await processCurrentFrame(frameIndex + 1, frame);
              }
            } catch (error) {
              decodeError = decodeError || error;
            } finally {
              try {
                frame.close();
              } catch (_) {}
              pendingOutputs = Math.max(0, pendingOutputs - 1);
              notifyOutputDrained();
            }
          });
        },
        error: (error) => {
          decodeError = decodeError || error;
        },
      });
      try {
        decoder.configure(demuxed.config);
        for (let i = 0; i < samples.length; i += 1) {
          checkAborted();
          if (decodeError) throw decodeError;
          const sample = samples[i];
          const sampleTimescale = sample.timescale || trackTimescale || fps;
          decoder.decode(new EncodedVideoChunk({
            type: sample.is_sync ? "key" : "delta",
            timestamp: microseconds(sample.cts ?? sample.dts ?? i, sampleTimescale),
            duration: microseconds(sample.duration || 1, sampleTimescale),
            data: sample.data,
          }));
          if (i % 20 === 0) {
            reportProgress({ processed, total: totalFramesEstimate, current_frame: i + 1, activeTracks: tracks.length, timings });
            await waitForDecoderQueue(decoder, 8);
            await waitForOutputBacklog();
          }
        }
        await decoder.flush();
        await outputChain;
        if (decodeError) throw decodeError;
        return true;
      } catch (error) {
        if (error && error.name === "AbortError") throw error;
        console.warn("[W-Agent] WebCodecs decode failed, falling back to video element:", error);
        return false;
      } finally {
        try {
          decoder.close();
        } catch (_) {}
      }
    }

    async function processWithContinuousDecode() {
      if (typeof video.requestVideoFrameCallback !== "function") return false;
      reportProgress({ stage: "decode", mode: "continuous" });
      video.currentTime = 0;
      const originalPlaybackRate = video.playbackRate || 1;
      try {
        video.playbackRate = 1;
      } catch (_) {
        // Some browsers reject playbackRate changes; decoding still works at 1x.
      }
      await video.play();
      let nextProcessTime = 0;
      try {
        while (!video.ended) {
          checkAborted();
          const decodeStart = performance.now();
          let metadata;
          try {
            metadata = await nextVideoFrame(video, 2500);
          } catch (error) {
            if (duration > 0 && video.currentTime >= duration - 0.35) break;
            if (isVideoFrameTimeout(error)) return false;
            throw error;
          }
          checkAborted();
          timings.seek_ms += performance.now() - decodeStart;
          video.pause();
          const mediaTime = Number.isFinite(metadata.mediaTime) ? metadata.mediaTime : video.currentTime;
          if (duration > 0 && mediaTime + 0.0005 < nextProcessTime) {
            await video.play();
            continue;
          }
          const frameID = Math.max(1, Math.round(mediaTime * fps) + 1);
          await processCurrentFrame(frameID);
          checkAborted();
          nextProcessTime += step;
          if (duration > 0 && nextProcessTime > duration) break;
          await video.play();
        }
      } finally {
        try {
          video.playbackRate = originalPlaybackRate;
        } catch (_) {}
        video.pause();
      }
      return true;
    }

    async function processWithSeekDecode() {
      reportProgress({ stage: "decode", mode: "seek" });
      for (let t = 0, frameID = 1; duration <= 0 || t <= duration; t += step, frameID += jump) {
        checkAborted();
        if (duration > 0) {
          const seekStart = performance.now();
          await seekVideo(video, Math.min(t, Math.max(0, duration - 0.001)));
          checkAborted();
          timings.seek_ms += performance.now() - seekStart;
        }
        await processCurrentFrame(frameID);
        if (duration <= 0) break;
      }
    }

    try {
      const usedWebCodecs = await processWithWebCodecsDecode();
      checkAborted();
      let usedContinuous = false;
      if (usedWebCodecs) {
        while (tracks.length) await finishTrack(tracks.shift());
      }
      if (!usedWebCodecs) {
        resetExtractionState();
        usedContinuous = await processWithContinuousDecode();
        checkAborted();
        if (usedContinuous) {
          while (tracks.length) await finishTrack(tracks.shift());
        }
      }
      if (!usedWebCodecs && !usedContinuous) {
        resetExtractionState();
        decodeMode = "seek_fallback";
        await processWithSeekDecode();
      } else if ((usedWebCodecs || usedContinuous) && completed.length === 0 && duration > 0) {
        resetExtractionState();
        decodeMode = "seek_fallback";
        await processWithSeekDecode();
      }
      checkAborted();
      while (tracks.length) await finishTrack(tracks.shift());
      if (!completed.length) throw new Error("未提取到满足长度和运动条件的人员序列，请换一个包含清晰行人的视频。");
      reportProgress({ stage: "done", processed, total: totalFramesEstimate, detected_sequences: completed.length });
      return {
        sequences: completed,
        meta: {
          video_width: rawW,
          video_height: rawH,
          processed_frames: processed,
          detected_sequences: completed.length,
          uploaded_sequences: completed.length,
          uploaded_frames: completed.reduce((sum, seq) => sum + seq.uploaded_frames, 0),
          detector_backend: detectorBackend,
          decode_mode: decodeMode,
          decode_playback_rate: cfg.decodePlaybackRate,
          rejected_short_sequences: rejectedShort,
          rejected_static_sequences: rejectedStatic,
          timings_ms: timings,
        },
        boxes: completed.flatMap((seq) => seq.boxes),
      };
    } catch (error) {
      if (error && error.name === "AbortError") {
        while (tracks.length) await finishTrack(tracks.shift(), { force: true });
        reportProgress({ stage: "aborted", processed, total: totalFramesEstimate, detected_sequences: completed.length });
      }
      throw error;
    } finally {
      cleanup();
    }
  }

  globalThis.WAgentPersonDet = {
    DEFAULT_CONFIG,
    PersonDetectorJS,
    PersonDetectorWasm,
    PersonDetectorOnnx,
    createDetector,
    extractLocalVideoSequence,
  };
}());
