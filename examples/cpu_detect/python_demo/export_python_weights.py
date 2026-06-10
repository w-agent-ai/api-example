from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CPP_WEIGHTS = ROOT / "cpp" / "persondet_weights.cpp"
OUT = ROOT / "python_demo" / "persondet_weights.py"


def parse_cpp_weights(text: str):
    shapes = {}
    arrays = {}

    for name, body in re.findall(r"static const unsigned int (g_[A-Za-z0-9_]+_shape)\[\] = \{([^}]*)\};", text):
        shapes[name] = [int(v.strip()) for v in body.split(",") if v.strip()]

    for name, body in re.findall(r"static const float (g_[A-Za-z0-9_]+)\[\] = \{(.*?)\};", text, flags=re.S):
        values = []
        for token in re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?f?", body):
            values.append(float(token.rstrip("fF")))
        arrays[name] = values

    records_match = re.search(r"const WeightBlob kWeights\[\] = \{(.*?)\};", text, flags=re.S)
    if not records_match:
        raise RuntimeError("kWeights table not found")

    records = []
    for blob_name, symbol, count, shape_symbol, ndim in re.findall(
        r'\{"([^"]+)",\s*(g_[A-Za-z0-9_]+),\s*(\d+),\s*(g_[A-Za-z0-9_]+_shape),\s*(\d+)\}',
        records_match.group(1),
    ):
        records.append((blob_name, symbol, int(count), shape_symbol, int(ndim)))
    return shapes, arrays, records


def main():
    text = CPP_WEIGHTS.read_text(encoding="utf-8")
    shapes, arrays, records = parse_cpp_weights(text)

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
    for blob_name, symbol, count, shape_symbol, ndim in records:
        shape = shapes[shape_symbol]
        values = arrays[symbol]
        if len(values) != count:
            raise RuntimeError(f"{blob_name}: expected {count}, got {len(values)}")
        if len(shape) != ndim:
            raise RuntimeError(f"{blob_name}: ndim mismatch")
        shape_text = ", ".join(str(v) for v in shape)
        value_text = ", ".join(f"{v:.9g}" for v in values)
        lines.append(f"    weights[{blob_name!r}] = np.array([{value_text}], dtype=np.float32).reshape(({shape_text},))")
    lines.extend(
        [
            "    return weights",
            "",
        ]
    )
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
