"""
handwriting_digits.py - Read handwritten digit strings locally (no LLM) from the pen layer of a page.

Tesseract is built for print, so handwritten IDs / dates were invisible to the local engine. Digits, unlike Hebrew
handwriting, are a solved problem: a small CNN trained on handwritten digits (MNIST, ONNX, ~26 KB) run with OpenCV.

    window of the pen layer (preprocessing.PageViews.handwriting) next to a label
      → connected components → keep the digit-like ones, grouped into the longest "word"
      → straighten the word's slant (baseline fit) → split touching digits
      → normalize every digit like MNIST (20x20 in 28x28, centred by mass) → CNN → probabilities per digit

Israeli IDs carry a check digit, so instead of trusting the top guess per digit, `best_id` searches the most
probable sequence that passes the check — a misread digit is then corrected, not only detected.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

import config
from domain.validators import israeli_id_is_valid


@dataclass(frozen=True)
class HandwritingSettings:
    # A component is digit-like when its height is within this range of the median component height...
    height_range: tuple[float, float] = (0.55, 1.7)
    # ...and it is not wider than this many heights (wider = touching digits, split below; much wider = cursive word).
    max_width_heights: float = 3.2
    # Components closer than this many median heights belong to the same written number (people group ID digits
    # with spaces, e.g. "112 23344" — measured on the samples).
    word_gap_heights: float = 1.6
    # A component wider than this many heights holds several touching digits (a single handwritten 3 or 4 is
    # about as wide as it is tall — measured — so a lower threshold cuts single digits in half).
    split_width_heights: float = 1.25
    # Typical width of one handwritten digit, in heights (used to count digits in a touching group).
    digit_width_heights: float = 0.75
    min_digits: int = 4
    # A blob may hold up to this many touching digits ("11" written in one stroke is narrow, so width alone
    # can't tell). Each split is tried; more pieces must raise the mean log-probability by this margin to win.
    max_pieces_per_blob: int = 3
    split_gain_nats: float = 0.4
    # Specks smaller than this share of the median component area are dots/noise (kept only as date separators).
    min_area_share: float = 0.15
    # Consider this many best guesses per digit when searching for a valid ID.
    id_top_k: int = 3


DEFAULT_SETTINGS = HandwritingSettings()


@dataclass
class DigitGuess:
    probs: np.ndarray  # shape (10,), softmax
    box: tuple[int, int, int, int]  # x, y, w, h in the window

    @property
    def best(self) -> int:
        return int(self.probs.argmax())

    @property
    def confidence(self) -> float:
        return float(self.probs.max())


@lru_cache(maxsize=1)
def _net():
    # Loaded from memory: OpenCV can't open files under non-ASCII paths on Windows (the project folder is Hebrew).
    return cv2.dnn.readNetFromONNX(np.fromfile(str(config.HANDWRITTEN_DIGITS_MODEL), dtype=np.uint8))


def is_available() -> bool:
    return config.HANDWRITTEN_DIGITS_MODEL.is_file()


def _to_mnist(mask: np.ndarray) -> np.ndarray:
    """A single digit (255 = ink) → 28x28 like MNIST: 20x20 box, centred by centre of mass, white on black."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((28, 28), np.float32)
    digit = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    height, width = digit.shape
    # Normalize stroke thickness (MNIST strokes are ~1/8 of the digit height).
    stroke = max(1, round(height / 14))
    digit = cv2.dilate(digit, np.ones((stroke, stroke), np.uint8))
    scale = 20.0 / max(height, width)
    resized = cv2.resize(digit, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((28, 28), np.uint8)
    y0, x0 = (28 - resized.shape[0]) // 2, (28 - resized.shape[1]) // 2
    canvas[y0:y0 + resized.shape[0], x0:x0 + resized.shape[1]] = resized
    moments = cv2.moments(canvas)
    if moments["m00"]:
        shift = np.float32([[1, 0, 14 - moments["m10"] / moments["m00"]], [0, 1, 14 - moments["m01"] / moments["m00"]]])
        canvas = cv2.warpAffine(canvas, shift, (28, 28))
    return canvas.astype(np.float32)


def classify(digit_masks: list[np.ndarray]) -> list[np.ndarray]:
    """Softmax probabilities per digit image."""
    net = _net()
    probabilities = []
    for mask in digit_masks:  # one at a time: the model has a fixed batch size of 1 (internal reshape)
        # Inputs must be 0..1 — with 0..255 the logits reach thousands and every softmax is a fake 100%.
        net.setInput(_to_mnist(mask)[None, None, :, :] / 255.0)
        logits = net.forward()[0]
        exp = np.exp(logits - logits.max())
        probabilities.append(exp / exp.sum())
    return probabilities


def _components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """(x, y, w, h, label) of ink blobs, with tiny gaps inside strokes closed first."""
    joined = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    return [(*stats[i, :4], i) for i in range(1, count)], labels


def _digit_word(mask: np.ndarray, settings: HandwritingSettings) -> np.ndarray | None:
    """Crop of the longest run of digit-like blobs (names and signatures nearby are left out)."""
    blobs, labels = _components(mask)
    blobs = [b for b in blobs if b[3] >= 6]
    if len(blobs) < 2:
        return None
    median_h = float(np.median([b[3] for b in blobs]))
    low, high = settings.height_range
    digit_like = [b for b in blobs if low * median_h <= b[3] <= high * median_h and b[2] <= settings.max_width_heights * b[3]]
    if not digit_like:
        return None
    # Lines first (by vertical centre), then words within a line (by horizontal gaps) — blobs of a signature
    # above the number can sit between its digits on the x axis and must not break the number apart.
    lines: list[list] = []
    for blob in sorted(digit_like, key=lambda b: b[1] + b[3] / 2):
        center = blob[1] + blob[3] / 2
        line = next((l for l in lines if abs(np.mean([b[1] + b[3] / 2 for b in l]) - center) < 0.6 * median_h), None)
        if line is None:
            lines.append([blob])
        else:
            line.append(blob)
    words = []
    for line in lines:
        line.sort(key=lambda b: b[0])
        current = [line[0]]
        for blob in line[1:]:
            if blob[0] - (current[-1][0] + current[-1][2]) <= settings.word_gap_heights * median_h:
                current.append(blob)
            else:
                words.append(current)
                current = [blob]
        words.append(current)

    def estimated_digits(word):
        return sum(max(1, round(b[2] / (settings.digit_width_heights * b[3]))) for b in word)

    word = max(words, key=estimated_digits)
    if estimated_digits(word) < settings.min_digits:
        return None
    keep = np.isin(labels, [b[4] for b in word])
    x0 = min(b[0] for b in word)
    y0 = min(b[1] for b in word)
    x1 = max(b[0] + b[2] for b in word)
    y1 = max(b[1] + b[3] for b in word)
    pad = max(2, int(median_h * 0.2))
    crop = np.where(keep, mask, 0).astype(np.uint8)
    return crop[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]


def _straighten(word: np.ndarray) -> np.ndarray:
    """Rotate so the baseline of the written number is horizontal (numbers are often written at a slant)."""
    blobs, _ = _components(word)
    if len(blobs) < 3:
        return word
    xs = np.array([b[0] + b[2] / 2 for b in blobs])
    ys = np.array([b[1] + b[3] for b in blobs], dtype=float)  # bottoms
    slope = np.polyfit(xs, ys, 1)[0]
    angle = float(np.degrees(np.arctan(slope)))
    if abs(angle) < 2:
        return word
    h, w = word.shape
    pad = int(w * abs(np.tan(np.radians(angle)))) + 4
    padded = cv2.copyMakeBorder(word, pad, pad, 4, 4, cv2.BORDER_CONSTANT, value=0)
    ph, pw = padded.shape
    matrix = cv2.getRotationMatrix2D((pw / 2, ph / 2), angle, 1.0)
    rotated = cv2.warpAffine(padded, matrix, (pw, ph), flags=cv2.INTER_NEAREST)
    ys_, xs_ = np.nonzero(rotated)
    return rotated[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1] if len(xs_) else word


def _split(blob_mask: np.ndarray, count: int) -> list[np.ndarray]:
    """Split touching digits at the thinnest columns near the equal-width cut points."""
    width = blob_mask.shape[1]
    profile = (blob_mask > 0).sum(axis=0)
    cuts, previous = [], 0
    for i in range(1, count):
        target = round(width * i / count)
        lo, hi = max(previous + 1, target - width // (3 * count)), min(width - 1, target + width // (3 * count))
        cut = lo + int(np.argmin(profile[lo:hi + 1])) if hi > lo else target
        cuts.append(cut)
        previous = cut
    edges = [0, *cuts, width]
    return [blob_mask[:, a:b] for a, b in zip(edges, edges[1:]) if b - a > 1]


def _window_slant(mask: np.ndarray, settings: HandwritingSettings) -> float:
    """Slant (degrees) of the handwriting in a window, from a robust line through the bottoms of digit-sized blobs.
    Needed BEFORE grouping blobs into a word: a number written uphill otherwise looks like several lines."""
    blobs, _ = _components(mask)
    blobs = [b for b in blobs if b[3] >= 6]
    if len(blobs) < 3:
        return 0.0
    median_h = float(np.median([b[3] for b in blobs]))
    low, high = settings.height_range
    blobs = [b for b in blobs if low * median_h <= b[3] <= high * median_h]
    if len(blobs) < 3:
        return 0.0
    xs = np.array([b[0] + b[2] / 2 for b in blobs], dtype=float)
    ys = np.array([b[1] + b[3] for b in blobs], dtype=float)
    keep = np.ones(len(xs), dtype=bool)
    for _ in range(2):  # refit without the worst outliers (other words at another height)
        slope, intercept = np.polyfit(xs[keep], ys[keep], 1)
        residuals = np.abs(ys - (slope * xs + intercept))
        keep = residuals <= max(median_h * 0.6, np.percentile(residuals, 70))
        if keep.sum() < 3:
            break
    return float(np.degrees(np.arctan(slope)))


def _rotate_mask(mask: np.ndarray, degrees: float) -> np.ndarray:
    h, w = mask.shape
    pad = int(max(h, w) * abs(np.sin(np.radians(degrees)))) + 4
    padded = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    ph, pw = padded.shape
    matrix = cv2.getRotationMatrix2D((pw / 2, ph / 2), degrees, 1.0)
    return cv2.warpAffine(padded, matrix, (pw, ph), flags=cv2.INTER_NEAREST)


def read_digits(window_mask: np.ndarray, settings: HandwritingSettings = DEFAULT_SETTINGS) -> list[DigitGuess]:
    """Digits of the main handwritten number in a pen-layer window (255 = ink), left to right."""
    if not is_available() or window_mask is None or window_mask.size == 0:
        return []
    slant = _window_slant(window_mask, settings)
    if abs(slant) >= 2:
        window_mask = _rotate_mask(window_mask, slant)
    word = _digit_word(window_mask, settings)
    if word is None:
        return []
    word = _straighten(word)
    blobs, labels = _components(word)
    if not blobs:
        return []
    median_h = float(np.median([b[3] for b in blobs]))
    median_area = float(np.median([b[2] * b[3] for b in blobs]))
    guesses: list[DigitGuess] = []
    for x, y, w, h, label in sorted(blobs, key=lambda b: b[0]):
        if w * h < settings.min_area_share * median_area or h < 0.4 * median_h:
            continue  # dots, dashes (date separators are re-inserted by the caller from the gaps)
        blob = np.where(labels[y:y + h, x:x + w] == label, 255, 0).astype(np.uint8)
        guesses.extend(_best_segmentation(blob, (x, y, h), settings))
    return guesses


def _best_segmentation(blob: np.ndarray, origin: tuple[int, int, int], settings: HandwritingSettings) -> list[DigitGuess]:
    """Read a blob as 1..max_pieces touching digits and keep the most convincing reading. The width-based
    estimate is the default; other piece counts must beat it by split_gain_nats (mean log-probability)."""
    x, y, h = origin
    width = blob.shape[1]
    estimate = max(1, round(width / (settings.digit_width_heights * h))) if width > settings.split_width_heights * h else 1
    best_score, best = None, []
    for count in sorted(range(1, settings.max_pieces_per_blob + 1), key=lambda c: c != estimate):
        parts = _split(blob, count) if count > 1 else [blob]
        if len(parts) != count or any(part.shape[1] < h * 0.15 for part in parts):
            continue  # a piece thinner than a stroke isn't a digit
        probabilities = classify(parts)
        score = float(np.mean([np.log(max(p.max(), 1e-9)) for p in probabilities]))
        margin = 0 if count == estimate else settings.split_gain_nats
        if best_score is None or score > best_score + margin:
            offsets = np.cumsum([0] + [p.shape[1] for p in parts[:-1]])
            best_score = score
            best = [DigitGuess(prob, (int(x + off), y, part.shape[1], h)) for prob, part, off in zip(probabilities, parts, offsets)]
    return best


def best_id(guesses: list[DigitGuess], settings: HandwritingSettings = DEFAULT_SETTINGS) -> tuple[str, float, bool] | None:
    """Most probable 8-9 digit sequence (top-k per digit) that passes the Israeli ID check digit.
    Returns (id, joint probability, corrected) — corrected=True when it differs from the top guess per digit."""
    if not 8 <= len(guesses) <= 9:
        return None
    options = [sorted(range(10), key=lambda d: -g.probs[d])[: settings.id_top_k] for g in guesses]
    log_probs = [np.log(np.maximum(g.probs, 1e-9)) for g in guesses]
    top = "".join(str(g.best) for g in guesses)
    # Enumerate in order of decreasing joint probability (best-first over the top-k grid).
    start = tuple(0 for _ in guesses)
    score = lambda idx: -sum(log_probs[i][options[i][k]] for i, k in enumerate(idx))  # noqa: E731
    heap, seen = [(score(start), start)], {start}
    while heap:
        cost, idx = heapq.heappop(heap)
        candidate = "".join(str(options[i][k]) for i, k in enumerate(idx))
        if israeli_id_is_valid(candidate):
            return candidate, float(np.exp(-cost)), candidate != top
        for i in range(len(idx)):
            if idx[i] + 1 < len(options[i]):
                nxt = idx[:i] + (idx[i] + 1,) + idx[i + 1:]
                if nxt not in seen:
                    seen.add(nxt)
                    heapq.heappush(heap, (score(nxt), nxt))
    return None


def as_text(guesses: list[DigitGuess]) -> str:
    return "".join(str(g.best) for g in guesses)


def mean_confidence(guesses: list[DigitGuess]) -> float:
    return float(np.mean([g.confidence for g in guesses])) if guesses else 0.0


__all__ = ["DigitGuess", "best_id", "classify", "is_available", "read_digits", "as_text", "mean_confidence"]
