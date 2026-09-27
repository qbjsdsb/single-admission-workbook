#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

NS = {"x": "http://www.w3.org/1999/xhtml"}

def words(path: Path):
    root = ET.parse(path).getroot()
    return [
        {
            "text": "".join(node.itertext()),
            "x": float(node.attrib["xMin"]),
            "y": float(node.attrib["yMin"]),
        }
        for node in root.findall(".//x:word", NS)
    ]

def first(items, pred, label):
    for item in items:
        if pred(item["text"]):
            return item
    raise AssertionError(f"cannot find {label}")

def close(label, actual, expected, tol=1.0):
    delta = abs(actual - expected)
    if delta > tol:
        raise AssertionError(
            f"{label}: x={actual:.3f}pt expected={expected:.3f}pt delta={delta:.3f}pt"
        )
    print(f"OK {label}: {actual:.3f}pt ~= {expected:.3f}pt")

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_e2e_layout.py <student-bbox.xhtml>")
    items = words(Path(sys.argv[1]))

    score = first(items, lambda t: t.startswith("（3"), "score rail")
    continuation = first(
        items,
        lambda t: t.startswith("行，并检查第二行以及后续行"),
        "wrapped politics stem continuation",
    )
    option_a = first(items, lambda t: t == "A.", "choice A rail")
    material_score = first(items, lambda t: t.startswith("（20"), "material score rail")

    close("wrapped stem -> score rail", continuation["x"], score["x"])
    close("choice A -> score rail", option_a["x"], score["x"])
    close("material score -> shared score rail", material_score["x"], score["x"])
    print("E2E layout geometry passed")

if __name__ == "__main__":
    main()
