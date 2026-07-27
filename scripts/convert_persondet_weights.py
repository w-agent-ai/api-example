#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


ARRAY_RE = re.compile(
    r"static const (?P<type>float|unsigned int) (?P<name>g_[A-Za-z0-9_]+(?:_shape)?)\[\] = \{(?P<body>.*?)\};",
    re.S,
)
WEIGHT_RE = re.compile(
    r'\{"(?P<name>[^"]+)",\s*(?P<data>g_[A-Za-z0-9_]+),\s*(?P<count>\d+),\s*(?P<shape>g_[A-Za-z0-9_]+_shape),\s*(?P<ndim>\d+)\}'
)


def parse_number_list(body: str) -> list[str]:
    body = re.sub(r"//.*", "", body)
    values = []
    for raw in body.replace("\n", " ").split(","):
        value = raw.strip()
        if not value:
            continue
        if value.endswith(("f", "F")):
            value = value[:-1]
        values.append(value)
    return values


def parse_cpp(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    arrays: dict[str, list[str]] = {}
    for match in ARRAY_RE.finditer(text):
        arrays[match.group("name")] = parse_number_list(match.group("body"))

    weights = []
    for match in WEIGHT_RE.finditer(text):
        name = match.group("name")
        data_key = match.group("data")
        shape_key = match.group("shape")
        count = int(match.group("count"))
        ndim = int(match.group("ndim"))
        if data_key not in arrays:
            raise SystemExit(f"missing data array for {name}: {data_key}")
        if shape_key not in arrays:
            raise SystemExit(f"missing shape array for {name}: {shape_key}")
        data = arrays[data_key]
        shape = [int(v) for v in arrays[shape_key]]
        if len(shape) != ndim:
            raise SystemExit(f"bad ndim for {name}: got shape {shape}, ndim {ndim}")
        if len(data) != count:
            raise SystemExit(f"bad count for {name}: got {len(data)}, expected {count}")
        if math.prod(shape) != count:
            raise SystemExit(f"bad shape count for {name}: shape {shape}, expected {count}")
        weights.append({"name": name, "shape": shape, "data": data})
    if not weights:
        raise SystemExit(f"no weights found in {path}")
    return weights


def fmt_list(values: list[str], indent: str = "        ", per_line: int = 8) -> str:
    lines = []
    for i in range(0, len(values), per_line):
        lines.append(indent + ", ".join(values[i : i + per_line]))
    return ",\n".join(lines)


def write_python(weights: list[dict[str, object]], path: Path) -> None:
    lines = [
        "# This file is generated from cpp/persondet_weights.cpp.",
        "# Runtime dependencies: numpy only.",
        "from __future__ import annotations",
        "",
        "import numpy as np",
        "",
        "def load_weights():",
        "    weights = {}",
    ]
    for item in weights:
        name = item["name"]
        shape = item["shape"]
        data = item["data"]
        lines.append(f"    weights[{name!r}] = np.array([")
        lines.append(fmt_list(data, "        "))
        lines.append(f"    ], dtype=np.float32).reshape(({', '.join(str(v) for v in shape)},))")
    lines.append("    return weights")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_js(weights: list[dict[str, object]], path: Path) -> None:
    lines = [
        "// This file is generated from cpp/persondet_weights.cpp.",
        "(function () {",
        '  "use strict";',
        "  const RAW_WEIGHTS = {",
    ]
    for item in weights:
        name = item["name"]
        shape = item["shape"]
        data = item["data"]
        lines.append(f"    {name!r}: {{ shape: [{', '.join(str(v) for v in shape)}], data: [")
        lines.append(fmt_list(data, "      "))
        lines.append("    ] },")
    lines.extend(
        [
            "  };",
            "  function load() {",
            "    const weights = {};",
            "    for (const [name, blob] of Object.entries(RAW_WEIGHTS)) {",
            "      weights[name] = { shape: blob.shape, data: new Float32Array(blob.data) };",
            "    }",
            "    return weights;",
            "  }",
            "  window.WAgentPersonDetWeights = { load };",
            "}());",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert persondet C++ weights to Python and browser JS weights.")
    parser.add_argument("cpp_weights", type=Path)
    parser.add_argument("--python-out", type=Path)
    parser.add_argument("--js-out", type=Path)
    args = parser.parse_args()

    weights = parse_cpp(args.cpp_weights)
    if args.python_out:
        write_python(weights, args.python_out)
    if args.js_out:
        write_js(weights, args.js_out)


if __name__ == "__main__":
    main()
