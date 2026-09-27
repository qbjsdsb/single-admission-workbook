#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {"x": "http://www.w3.org/1999/xhtml"}


def words(page):
    out = []
    for node in page.findall(".//x:word", NS):
        out.append(
            {
                "text": "".join(node.itertext()),
                "x": float(node.attrib["xMin"]),
                "y": float(node.attrib["yMin"]),
            }
        )
    return out


def first_x(items, predicate, label):
    for item in items:
        if predicate(item["text"]):
            return item["x"]
    raise AssertionError(f"cannot find {label}")


def assert_close(name, actual, expected, tol=1.0):
    delta = abs(actual - expected)
    if delta > tol:
        raise AssertionError(
            f"{name}: x={actual:.3f}pt, expected {expected:.3f}pt, delta={delta:.3f}pt"
        )
    print(f"OK {name}: {actual:.3f}pt ~= {expected:.3f}pt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bbox_xhtml", type=Path)
    args = ap.parse_args()

    root = ET.parse(args.bbox_xhtml).getroot()
    pages = root.findall(".//x:page", NS)
    if len(pages) != 4:
        raise AssertionError(f"expected 4 prototype pages, got {len(pages)}")

    math = words(pages[1])
    politics = words(pages[2])

    politics_score_x = first_x(
        politics, lambda t: t.startswith("（3"), "politics score rail"
    )
    politics_continuation_x = first_x(
        politics,
        lambda t: "到的“三个主要的法宝”" in t,
        "politics wrapped continuation line",
    )
    assert_close(
        "politics wrapped stem -> score rail",
        politics_continuation_x,
        politics_score_x,
    )

    math_score_x = first_x(math, lambda t: t.startswith("（18"), "math score rail")
    math_part_x = first_x(
        math, lambda t: t.startswith("（1）"), "math first sub-question"
    )
    assert_close("math sub-question -> score rail", math_part_x, math_score_x)

    choice_x = first_x(politics, lambda t: t == "A.", "politics choice rail")
    assert_close("politics choice -> score rail", choice_x, politics_score_x)

    print("layout bbox contract passed")


if __name__ == "__main__":
    main()
