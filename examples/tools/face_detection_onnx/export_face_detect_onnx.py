#!/usr/bin/env python3
"""Export Shiqi Yu libfacedetection C++ weights to an ONNX backbone.

The original library compiles model weights into `facedetectcnn-data.cpp`.
This exporter keeps the same network topology and exports the convolutional
forward pass. Image pre-processing and detection post-processing intentionally
stay in client code so Python and C++ can share a small, fixed ONNX Runtime
model in the same style as the existing person detector.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


@dataclass(frozen=True)
class ConvInfo:
    channels: int
    num_filters: int
    is_depthwise: bool
    is_pointwise: bool
    with_relu: bool
    weight_name: str
    bias_name: str


def parse_float_array(text: str) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    pattern = re.compile(
        r"float\s+([A-Za-z0-9_]+)\s*\[([^\]]+)\]\s*=\s*\{(.+?)\};",
        re.S,
    )
    for name, _shape_expr, body in pattern.findall(text):
        body = body.replace("\n", " ").replace("f", "")
        values = ast.literal_eval("[" + body + "]")
        arrays[name] = np.asarray(values, dtype=np.float32)
    return arrays


def parse_conv_info(text: str) -> list[ConvInfo]:
    match = re.search(r"ConvInfoStruct\s+param_pConvInfo\s*\[53\]\s*=\s*\{(.+?)\};", text, re.S)
    if not match:
        raise ValueError("param_pConvInfo[53] not found")
    entries = re.findall(
        r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(true|false)\s*,\s*(true|false)\s*,\s*(true|false)\s*,\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\}",
        match.group(1),
    )
    if len(entries) != 53:
        raise ValueError(f"expected 53 conv entries, found {len(entries)}")
    out: list[ConvInfo] = []
    for channels, num_filters, is_depthwise, is_pointwise, with_relu, weight, bias in entries:
        out.append(
            ConvInfo(
                channels=int(channels),
                num_filters=int(num_filters),
                is_depthwise=is_depthwise == "true",
                is_pointwise=is_pointwise == "true",
                with_relu=with_relu == "true",
                weight_name=weight,
                bias_name=bias,
            )
        )
    return out


class GraphBuilder:
    def __init__(self, arrays: dict[str, np.ndarray], convs: list[ConvInfo]):
        self.arrays = arrays
        self.convs = convs
        self.nodes: list[onnx.NodeProto] = []
        self.initializers: list[onnx.TensorProto] = []
        self.counter = 0

    def tensor(self, name: str, value: np.ndarray) -> str:
        self.initializers.append(numpy_helper.from_array(value.astype(np.float32), name))
        return name

    def unique(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}_{self.counter}"

    def conv(self, x: str, index: int, do_relu: bool | None = None) -> str:
        info = self.convs[index]
        weights = self.arrays[info.weight_name]
        biases = self.arrays[info.bias_name]
        if info.is_pointwise and not info.is_depthwise:
            weight = weights.reshape(info.num_filters, info.channels, 1, 1)
            group = 1
            pads = [0, 0, 0, 0]
        elif info.is_depthwise and not info.is_pointwise:
            weight = weights.reshape(9, info.channels).T.reshape(info.channels, 1, 3, 3)
            group = info.channels
            pads = [1, 1, 1, 1]
        else:
            raise ValueError(f"unsupported conv entry {index}: {info}")
        if biases.shape[0] != info.num_filters:
            raise ValueError(f"bias shape mismatch at conv {index}: {biases.shape}")
        y = self.unique(f"conv{index}")
        self.nodes.append(
            helper.make_node(
                "Conv",
                [x, self.tensor(f"conv{index}_weight", weight), self.tensor(f"conv{index}_bias", biases)],
                [y],
                name=f"conv{index}",
                kernel_shape=list(weight.shape[2:]),
                pads=pads,
                strides=[1, 1],
                group=group,
            )
        )
        if info.with_relu if do_relu is None else do_relu:
            relu = self.unique(f"relu{index}")
            self.nodes.append(helper.make_node("Relu", [y], [relu], name=f"relu{index}"))
            return relu
        return y

    def conv_dp(self, x: str, pointwise_index: int, depthwise_index: int, do_relu: bool = True) -> str:
        x = self.conv(x, pointwise_index, do_relu=False)
        return self.conv(x, depthwise_index, do_relu=do_relu)

    def conv4(self, x: str, p1: int, d1: int, p2: int, d2: int, do_relu: bool = True) -> str:
        x = self.conv_dp(x, p1, d1, do_relu=True)
        return self.conv_dp(x, p2, d2, do_relu=do_relu)

    def maxpool(self, x: str, name: str) -> str:
        y = self.unique(name)
        self.nodes.append(
            helper.make_node(
                "MaxPool",
                [x],
                [y],
                name=name,
                kernel_shape=[2, 2],
                strides=[2, 2],
                ceil_mode=1,
            )
        )
        return y

    def upsample_x2(self, x: str, name: str) -> str:
        # The original C++ copies each pixel to a 2x2 block. Nearest Resize with
        # asymmetric mode matches that behavior for scale=2.
        scales = self.tensor(f"{name}_scales", np.asarray([1.0, 1.0, 2.0, 2.0], dtype=np.float32))
        y = self.unique(name)
        self.nodes.append(
            helper.make_node(
                "Resize",
                [x, "", scales],
                [y],
                name=name,
                mode="nearest",
                coordinate_transformation_mode="asymmetric",
                nearest_mode="floor",
            )
        )
        return y

    def add(self, a: str, b: str, name: str) -> str:
        y = self.unique(name)
        self.nodes.append(helper.make_node("Add", [a, b], [y], name=name))
        return y

    def build(self) -> onnx.ModelProto:
        x = "preprocessed"

        x = self.conv(x, 0)
        x = self.conv_dp(x, 1, 2)
        x = self.maxpool(x, "pool0")
        x = self.conv4(x, 3, 4, 5, 6)
        x = self.conv4(x, 7, 8, 9, 10)
        x = self.maxpool(x, "pool3")
        fb1 = self.conv4(x, 11, 12, 13, 14)
        x = self.maxpool(fb1, "pool4")
        fb2 = self.conv4(x, 15, 16, 17, 18)
        x = self.maxpool(fb2, "pool5")
        fb3 = self.conv4(x, 19, 20, 21, 22)

        fb3 = self.conv_dp(fb3, 27, 28)
        pred_cls2 = self.conv_dp(fb3, 33, 34, do_relu=False)
        pred_reg2 = self.conv_dp(fb3, 39, 40, do_relu=False)
        pred_kps2 = self.conv_dp(fb3, 51, 52, do_relu=False)
        pred_obj2 = self.conv_dp(fb3, 45, 46, do_relu=False)

        fb2 = self.add(self.upsample_x2(fb3, "upsample5"), fb2, "add5")
        fb2 = self.conv_dp(fb2, 25, 26)
        pred_cls1 = self.conv_dp(fb2, 31, 32, do_relu=False)
        pred_reg1 = self.conv_dp(fb2, 37, 38, do_relu=False)
        pred_kps1 = self.conv_dp(fb2, 49, 50, do_relu=False)
        pred_obj1 = self.conv_dp(fb2, 43, 44, do_relu=False)

        fb1 = self.add(self.upsample_x2(fb2, "upsample4"), fb1, "add4")
        fb1 = self.conv_dp(fb1, 23, 24)
        pred_cls0 = self.conv_dp(fb1, 29, 30, do_relu=False)
        pred_reg0 = self.conv_dp(fb1, 35, 36, do_relu=False)
        pred_kps0 = self.conv_dp(fb1, 47, 48, do_relu=False)
        pred_obj0 = self.conv_dp(fb1, 41, 42, do_relu=False)

        outputs = [
            ("cls8", pred_cls0, 1),
            ("reg8", pred_reg0, 4),
            ("kps8", pred_kps0, 10),
            ("obj8", pred_obj0, 1),
            ("cls16", pred_cls1, 1),
            ("reg16", pred_reg1, 4),
            ("kps16", pred_kps1, 10),
            ("obj16", pred_obj1, 1),
            ("cls32", pred_cls2, 1),
            ("reg32", pred_reg2, 4),
            ("kps32", pred_kps2, 10),
            ("obj32", pred_obj2, 1),
        ]
        for public_name, internal_name, _channels in outputs:
            if public_name != internal_name:
                self.nodes.append(helper.make_node("Identity", [internal_name], [public_name], name=f"id_{public_name}"))

        graph = helper.make_graph(
            self.nodes,
            "w_agent_face_detect",
            [helper.make_tensor_value_info("preprocessed", TensorProto.FLOAT, ["N", 32, "H", "W"])],
            [helper.make_tensor_value_info(name, TensorProto.FLOAT, ["N", channels, "OH", "OW"]) for name, _, channels in outputs],
            self.initializers,
        )
        model = helper.make_model(
            graph,
            producer_name="w-agent-libfacedetection-export",
            opset_imports=[helper.make_operatorsetid("", 13)],
        )
        model.ir_version = min(model.ir_version, 10)
        onnx.checker.check_model(model)
        return model


def export(source: Path, output: Path) -> None:
    text = source.read_text(encoding="utf-8")
    arrays = parse_float_array(text)
    convs = parse_conv_info(text)
    model = GraphBuilder(arrays, convs).build()
    output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("examples/registered/cpp/face_feature_demo/third_party/libfacedetection/src/facedetectcnn-data.cpp"),
        help="path to libfacedetection facedetectcnn-data.cpp",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/registered/cpp/face_feature_demo/face_detect.onnx"),
        help="output ONNX path",
    )
    args = parser.parse_args()
    export(args.source, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
