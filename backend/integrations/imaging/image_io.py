from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path) -> np.ndarray:
    """cv2.imread can't open non-ASCII paths on Windows (the project folder is Hebrew) — decode from bytes."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode image {path.name}")
    return image


def png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Cannot encode image")
    return encoded.tobytes()
