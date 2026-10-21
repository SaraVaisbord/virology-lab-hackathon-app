"""
local_extractor.py - Deterministic, local field extraction (no LLM, no tokens).

Pipeline for one preprocessed page (see preprocessing.py):
  1. OCR the clean print layer (labels, printed numbers) → words with boxes and confidence.
  2. Split glued tokens ("מרכזי:12043017" → label "מרכזי:" + number "12043017").
  3. Find label lines from LOCAL_LABEL_LEXICON (fuzzy: one wrong letter allowed — "מרכדי" still matches "מרכזי").
     The health fund is recognised from the page (FORM_TYPE_MARKERS) — some labels exist only on its forms.
  4. Collect value tokens (numbers / dates) and drop those on lines with negative labels (catalog no., phone…).
  5. Pair every label with the nearest suitable value: on the same line to its LEFT (Hebrew reads right-to-left),
     or right below it. Barcodes next to a label are candidates too.
  6. When a label has no value, OCR just the area next to it again, digits only, on several image variants.
  7. The received date is the one written right under the central number: such dates are candidates first.

Every candidate carries its evidence: source, OCR confidence, the label text and box, and the distance to it.
Coordinates are normalized to the page (0..1). Unpaired numbers are kept (never silently dropped).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

import cv2

import config
import ocr_reader
from db.constants import (
    DATE_PATTERN,
    FIELD_KINDS,
    FORM_TYPE_LABEL_KEYWORDS,
    FORM_TYPE_MARKERS,
    HEBREW_PREFIXES,
    LOCAL_LABEL_LEXICON,
    LOCAL_NEGATIVE_LABELS,
    MULTI_VALUE_FIELDS,
    RECEIVED_DATE_ANCHOR_LABEL,
)
from ocr_reader import OcrWord
from preprocessing import PageViews
from validators import israeli_id_is_valid


@dataclass(frozen=True)
class LocalExtractionSettings:
    # Words OCR is less sure about than this are ignored (Tesseract confidence 0..100).
    min_word_confidence: float = 35
    # One wrong letter is tolerated in label keywords of at least this length ("מרכדי" → "מרכזי").
    fuzzy_min_keyword_length: int = 4
    # Two words are on the same line when their vertical centres differ by less than this share of their height.
    same_line_tolerance: float = 0.6
    # Pairing limits (page widths): a value left of its label, or below it.
    max_same_line_gap: float = 0.30
    max_below_gap_label_heights: float = 3.5
    max_below_x_offset: float = 0.15
    # A value on the label's right side (unusual in Hebrew forms) costs this extra distance.
    right_side_penalty: float = 0.08
    # Digit counts accepted per field kind. IDs: 8-9 digits — with fewer, a random number passes the
    # check digit 1 time in 10 (seen on the samples: a 6-digit date fragment accepted as an ID).
    number_digits: tuple[int, int] = (4, 10)
    id_digits: tuple[int, int] = (8, 9)
    # A generic label ("תאריך") counts as this much extra distance compared to a specific one ("ת.קבלה").
    weak_label_penalty: float = 0.06
    # Targeted OCR: window next to a label (page widths / label heights), upscaling, character whitelist.
    targeted_window_width: float = 0.35
    targeted_window_below_heights: float = 4.0
    targeted_upscale: float = 2.0
    targeted_whitelist: str = "0123456789./-"
    targeted_min_confidence: float = 50
    # Barcode stickers: their own label ("מרכזי:") is small and often missed by the full-page OCR, so the area
    # around every barcode is OCR'd again (Hebrew + digits). Window = barcode box grown by these factors.
    sticker_grow_x: float = 1.5  # times the barcode width, on each side
    sticker_grow_y: float = 3.0  # times the barcode height, above and below
    # Received date under the central number: at most this far below it (page heights) and this far off its
    # horizontal centre (page widths) — the "התקבל" stamp / handwritten date sits right beneath the sticker.
    anchor_max_gap: float = 0.08
    anchor_max_x_offset: float = 0.15


DEFAULT_SETTINGS = LocalExtractionSettings()

_DATE = re.compile(DATE_PATTERN)
_GLUED = re.compile(r"^(\D{2,}?)[:׃\s]*(\d[\d./\-]{3,})$")  # "מרכזי:12043017"
_PHONE = re.compile(r"^\+?\d{1,3}-\d|^0\d{1,2}-\d{6,8}$|^\+972")


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def union(self, other: "Box") -> "Box":
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Box(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)


@dataclass
class Token:
    text: str
    box: Box
    confidence: float
    source: str  # "ocr" | "ocr_targeted" | "barcode"
    negative: bool = False


@dataclass
class Label:
    field: str
    text: str
    box: Box
    strong: bool = True  # False for generic labels (plain "תאריך") — they lose to specific ones


@dataclass
class Candidate:
    field: str
    value: str  # normalized: digits only for numbers, DD/MM/YYYY for dates
    raw: str  # exactly as read
    source: str
    confidence: float
    box: dict
    label: str
    label_box: dict
    distance: float  # geometric distance + weak-label penalty (lower is better)
    rank: int = 0  # 0 = best candidate for its field; single-value fields use rank 0, the rest are alternatives
    anchor: str | None = None  # "central_number": a received date found right under a central number


@dataclass
class LocalResult:
    candidates: list[Candidate] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    unassigned_numbers: list[dict] = field(default_factory=list)
    form_type: str | None = None

    def as_dict(self) -> dict:
        return {
            "form_type": self.form_type,
            "candidates": [asdict(c) for c in self.candidates],
            "labels": [{"field": l.field, "text": l.text, "box": asdict(l.box)} for l in self.labels],
            "unassigned_numbers": self.unassigned_numbers,
        }


# ── text helpers ─────────────────────────────────────────────────────────────


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _clean_word(text: str) -> str:
    return text.strip(":;,.()׃\"'״׳-– ")


def _matches(word: str, keyword: str, settings: LocalExtractionSettings) -> bool:
    """Whole-word match, optionally with one Hebrew prefix letter ("ההתחייבות", "מתאריך"), or the same length
    with ONE substituted letter (an OCR misread such as "מרכדי" for "מרכזי"). No substring matches: "מרכזית"
    (feminine, e.g. a central pharmacy) must not match "מרכזי", nor "מרכז" (centre)."""
    word = _clean_word(word)
    keyword = _clean_word(keyword)
    forms = [word] + ([word[1:]] if len(word) > len(keyword) and word[:1] in HEBREW_PREFIXES else [])
    for form in forms:
        if form == keyword:
            return True
        if len(keyword) >= settings.fuzzy_min_keyword_length and len(form) == len(keyword) and _edit_distance(form, keyword) == 1:
            return True
    return False


def normalize_date(text: str) -> str | None:
    match = _DATE.search(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    if len(match.group(3)) == 2:
        year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return f"{day:02d}/{month:02d}/{year}"


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


# ── tokens & lines ───────────────────────────────────────────────────────────


def _tokens_from_words(words: list[OcrWord], settings: LocalExtractionSettings, source: str = "ocr") -> list[Token]:
    tokens = []
    for word in words:
        if word.confidence < settings.min_word_confidence:
            continue
        box = Box(word.x, word.y, word.width, word.height)
        glued = _GLUED.match(word.text)
        if glued:
            label_text, number = glued.groups()
            share = len(label_text) / len(word.text)  # Hebrew label is on the right of the glued token
            tokens.append(Token(label_text, Box(box.x + box.width * (1 - share), box.y, box.width * share, box.height), word.confidence, source))
            tokens.append(Token(number, Box(box.x, box.y, box.width * (1 - share), box.height), word.confidence, source))
        else:
            tokens.append(Token(word.text, box, word.confidence, source))
    return tokens


def _group_lines(tokens: list[Token], settings: LocalExtractionSettings) -> list[list[Token]]:
    lines: list[list[Token]] = []
    for token in sorted(tokens, key=lambda t: t.box.center_y):
        for line in lines:
            reference = line[0].box
            if abs(reference.center_y - token.box.center_y) < settings.same_line_tolerance * max(reference.height, token.box.height):
                line.append(token)
                break
        else:
            lines.append([token])
    return lines


def detect_form_type(texts: list[str], settings: LocalExtractionSettings | None = None) -> str | None:
    """The form type whose marker word (FORM_TYPE_MARKERS) is on the page — None when none or several are."""
    settings = settings or DEFAULT_SETTINGS
    found = {form_type for form_type, markers in FORM_TYPE_MARKERS.items()
             if any(_matches(text, marker, settings) for text in texts for marker in markers)}
    return found.pop() if len(found) == 1 else None


def _find_labels(lines: list[list[Token]], settings: LocalExtractionSettings, form_type: str | None = None) -> list[Label]:
    type_keywords = FORM_TYPE_LABEL_KEYWORDS.get(form_type or "", {})
    labels = []
    for line in lines:
        texts = [t.text for t in line]
        for field_name, spec in LOCAL_LABEL_LEXICON.items():
            hits = [t for t in line if any(_matches(t.text, k, settings) for k in spec["keywords"])]
            # Labels of this form type only (Leumit "דגימה"): the page already says which form it is.
            type_hits = [t for t in line if any(_matches(t.text, k, settings) for k in type_keywords.get(field_name, ()))]
            if not hits and not type_hits:
                continue
            if any(_matches(text, word, settings) for text in texts for word in spec["exclude_if_line_has"]):
                continue
            required = [t for t in line if any(_clean_word(t.text) == w.strip("'׳") or t.text.startswith(w) for w in spec["requires_one_of"])]
            if not type_hits and spec["requires_one_of"] and not required:
                continue
            hits = hits + type_hits
            box = hits[0].box
            for token in hits[1:] + required:
                box = box.union(token.box)
            words = dict.fromkeys(t.text for t in sorted(hits + required, key=lambda t: -t.box.x))  # RTL order, no repeats
            strong_words = spec.get("strong_keywords")
            strong = not strong_words or any(_matches(t.text, k, settings) for t in hits for k in strong_words)
            labels.append(Label(field_name, " ".join(words), box, strong))
    return labels


def _mark_negative(lines: list[list[Token]]) -> None:
    for line in lines:
        if any(_clean_word(t.text) in {_clean_word(n) for n in LOCAL_NEGATIVE_LABELS} or t.text.startswith(LOCAL_NEGATIVE_LABELS) for t in line):
            for token in line:
                token.negative = True


def _value_for_field(token: Token, field_name: str, settings: LocalExtractionSettings) -> str | None:
    """The normalized value if the token can be this field's value, else None."""
    if token.negative or _PHONE.search(token.text):
        return None
    kind = FIELD_KINDS[field_name]
    if kind == "date":
        value = normalize_date(token.text)
        if value is None:
            return None
        day, month, year = (int(p) for p in value.split("/"))
        try:
            age_days = (date.today() - date(year, month, day)).days
        except ValueError:  # e.g. 31/02
            return None
        # Same plausibility window the verification rules use (printed form-version dates are years old).
        return value if 0 <= age_days <= config.RECEIVED_DATE_MAX_AGE_DAYS else None
    if normalize_date(token.text):  # a date is never a number field
        return None
    digits = _digits(token.text)
    if not re.fullmatch(r"[\d\s./\-]+", token.text.strip(":׃")):
        return None
    low, high = settings.id_digits if kind == "id" else settings.number_digits
    if not low <= len(digits) <= high:
        return None
    if kind == "id" and not israeli_id_is_valid(digits):  # a misread ID almost always breaks the check digit
        return None
    return digits


def _distance(label: Box, value: Box, settings: LocalExtractionSettings) -> float | None:
    """Geometric distance from a label to a value token in page widths, or None if not a plausible pair."""
    same_line = abs(label.center_y - value.center_y) < settings.same_line_tolerance * max(label.height, value.height)
    if same_line:
        if value.right <= label.x + label.width * 0.2:  # left of the label (RTL: value follows the label)
            gap = label.x - value.right
            return max(gap, 0.0) if gap <= settings.max_same_line_gap else None
        if value.x >= label.right - label.width * 0.2:  # right of the label
            gap = value.x - label.right
            return max(gap, 0.0) + settings.right_side_penalty if gap <= settings.max_same_line_gap else None
        return None
    below_gap = value.y - label.bottom
    if -label.height * 0.3 <= below_gap <= settings.max_below_gap_label_heights * label.height:
        x_offset = abs((value.x + value.width / 2) - (label.x + label.width / 2))
        if x_offset <= settings.max_below_x_offset:
            return below_gap * 1.41 + x_offset  # 1.41 ≈ A4 height/width, so both axes are in page widths
    return None


def _pair(labels: list[Label], tokens: list[Token], settings: LocalExtractionSettings) -> list[Candidate]:
    """Greedy best-first pairing: every label gets its nearest value, and every token is used once."""
    options = []
    for li, label in enumerate(labels):
        for ti, token in enumerate(tokens):
            value = _value_for_field(token, label.field, settings)
            if value is None:
                continue
            distance = _distance(label.box, token.box, settings)
            if distance is not None:
                options.append((distance + (0 if label.strong else settings.weak_label_penalty), li, ti, value))
    used_labels, used_tokens, candidates = set(), set(), []
    for distance, li, ti, value in sorted(options):
        if li in used_labels or ti in used_tokens:
            continue
        used_labels.add(li)
        used_tokens.add(ti)
        label, token = labels[li], tokens[ti]
        candidates.append(Candidate(label.field, value, token.text, token.source, token.confidence,
                                    asdict(token.box), label.text, asdict(label.box), round(distance, 4)))
    return candidates


def _dates_under_central(candidates: list[Candidate], tokens: list[Token], settings: LocalExtractionSettings) -> list[Candidate]:
    """The received date is written (or stamped "התקבל") right under the central number — one per central number."""
    found = []
    for central in (c for c in candidates if c.field == "central_number"):
        anchor = Box(**central.box)
        options = []
        for token in tokens:
            value = _value_for_field(token, "received_date", settings)
            if value is None:
                continue
            gap = token.box.y - anchor.bottom
            x_offset = abs((token.box.x + token.box.width / 2) - (anchor.x + anchor.width / 2))
            if -anchor.height * 0.3 <= gap <= settings.anchor_max_gap and x_offset <= settings.anchor_max_x_offset:
                options.append((max(gap, 0.0) * 1.41 + x_offset, token, value))  # 1.41 ≈ A4 height/width
        if options:
            distance, token, value = min(options, key=lambda option: option[0])
            found.append(Candidate("received_date", value, token.text, token.source, token.confidence, asdict(token.box),
                                   RECEIVED_DATE_ANCHOR_LABEL.format(value=central.value), central.box, round(distance, 4),
                                   anchor="central_number"))
    return found


# ── targeted OCR next to a label ─────────────────────────────────────────────


def _targeted_tokens(views: PageViews, label: Label, settings: LocalExtractionSettings) -> list[Token]:
    """OCR only the window next to a label (left of it and below it), digits only, on several image variants."""
    height, width = views.print_binary.shape[:2]
    x0 = max(0.0, label.box.x - settings.targeted_window_width)
    y0 = max(0.0, label.box.y - label.box.height * 0.5)
    x1 = min(1.0, label.box.right + label.box.width * 0.2)
    y1 = min(1.0, label.box.bottom + label.box.height * settings.targeted_window_below_heights)
    px0, py0, px1, py1 = int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)
    if px1 - px0 < 10 or py1 - py0 < 10:
        return []

    gray = cv2.cvtColor(views.normalized, cv2.COLOR_BGR2GRAY)
    variants = [views.print_binary[py0:py1, px0:px1], gray[py0:py1, px0:px1]]
    tokens = []
    for crop in variants:
        crop = cv2.resize(crop, None, fx=settings.targeted_upscale, fy=settings.targeted_upscale, interpolation=cv2.INTER_CUBIC)
        crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        words = ocr_reader.read_words(crop, psm=11, languages="eng", extra_config=["-c", f"tessedit_char_whitelist={settings.targeted_whitelist}"])
        ch, cw = crop.shape[:2]
        for word in words:
            if word.confidence < settings.targeted_min_confidence:
                continue
            # map crop coordinates (with border and upscale) back to the page
            wx = ((word.x * cw - 20) / settings.targeted_upscale + px0) / width
            wy = ((word.y * ch - 20) / settings.targeted_upscale + py0) / height
            ww = (word.width * cw / settings.targeted_upscale) / width
            wh = (word.height * ch / settings.targeted_upscale) / height
            tokens.append(Token(word.text, Box(wx, wy, ww, wh), word.confidence, "ocr_targeted"))
    return tokens


def _crop_words(image, box: Box, settings: LocalExtractionSettings, languages: str | None = None,
                extra_config: list[str] | None = None, min_confidence: float | None = None) -> list[OcrWord]:
    """OCR a page region (normalized box), upscaled, and return words with page-normalized coordinates."""
    height, width = image.shape[:2]
    px0, py0 = max(0, int(box.x * width)), max(0, int(box.y * height))
    px1, py1 = min(width, int(box.right * width)), min(height, int(box.bottom * height))
    if px1 - px0 < 10 or py1 - py0 < 10:
        return []
    border, scale = 20, settings.targeted_upscale
    crop = cv2.resize(image[py0:py1, px0:px1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    crop = cv2.copyMakeBorder(crop, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
    ch, cw = crop.shape[:2]
    words = []
    for word in ocr_reader.read_words(crop, psm=11, languages=languages, extra_config=extra_config):
        if min_confidence is not None and word.confidence < min_confidence:
            continue
        words.append(OcrWord(
            text=word.text, confidence=word.confidence,
            x=((word.x * cw - border) / scale + px0) / width, y=((word.y * ch - border) / scale + py0) / height,
            width=(word.width * cw / scale) / width, height=(word.height * ch / scale) / height,
            line_key=word.line_key,
        ))
    return words


def _sticker_words(views: PageViews, barcodes: list[dict], settings: LocalExtractionSettings) -> list[OcrWord]:
    """Re-read the sticker around every barcode — its label and printed number sit right next to the bars."""
    gray = cv2.cvtColor(views.normalized, cv2.COLOR_BGR2GRAY)
    words = []
    for barcode in barcodes:
        if not barcode.get("width"):
            continue
        window = Box(
            barcode["x"] - barcode["width"] * settings.sticker_grow_x,
            barcode["y"] - barcode["height"] * settings.sticker_grow_y,
            barcode["width"] * (1 + 2 * settings.sticker_grow_x),
            barcode["height"] * (1 + 2 * settings.sticker_grow_y),
        )
        words.extend(_crop_words(gray, window, settings))
    return words


# ── entry point ──────────────────────────────────────────────────────────────


def _overlap(a: Box, b: Box) -> float:
    w = min(a.right, b.right) - max(a.x, b.x)
    h = min(a.bottom, b.bottom) - max(a.y, b.y)
    if w <= 0 or h <= 0:
        return 0.0
    return (w * h) / min(a.width * a.height, b.width * b.height)


def read_page_words(views: PageViews) -> list[OcrWord]:
    """OCR the clean print layer AND the (deskewed, highlighter-free) grey page: labels on stickers or small
    print are often lost in one of them but read in the other. Both passes are kept as they are — the two
    readings of one spot may differ (e.g. "מסרה:12043017" vs "12043017") and each can carry different evidence;
    pairing uses every token at most once and duplicates are removed from the unassigned list."""
    gray = cv2.cvtColor(views.normalized, cv2.COLOR_BGR2GRAY)
    return ocr_reader.read_words(views.print_binary) + ocr_reader.read_words(gray)


def extract(views: PageViews, barcodes: list[dict] | None = None, words: list[OcrWord] | None = None,
            settings: LocalExtractionSettings = DEFAULT_SETTINGS) -> LocalResult:
    words = read_page_words(views) if words is None else words
    words = words + _sticker_words(views, barcodes or [], settings)
    tokens = _tokens_from_words(words, settings)
    form_type = detect_form_type([t.text for t in tokens], settings)
    lines = _group_lines(tokens, settings)
    _mark_negative(lines)
    # The two OCR passes often both read the same printed label — keep one, or it would claim two values.
    labels: list[Label] = []
    for label in _find_labels(lines, settings, form_type):
        if not any(l.field == label.field and _overlap(l.box, label.box) > 0.3 for l in labels):
            labels.append(label)

    barcode_tokens = [
        Token(b["data"], Box(b["x"], b["y"], b["width"], b["height"]), 100.0, "barcode")
        for b in barcodes or [] if b.get("data") and b.get("width")
    ]
    candidates = _pair(labels, tokens + barcode_tokens, settings)

    # Labels still without a value: read the area next to them again, digits only.
    paired = {(c.field, c.label_box["x"], c.label_box["y"]) for c in candidates}
    for label in labels:
        if (label.field, label.box.x, label.box.y) in paired:
            continue
        extra = _pair([label], _targeted_tokens(views, label, settings), settings)
        candidates.extend(extra)
    candidates.extend(_dates_under_central(candidates, tokens, settings))

    # Rank candidates per field (best first; a date under the central number before any labelled date). Single-value
    # fields use rank 0; the rest stay as alternatives. The same value found twice (two OCR passes, or OCR + barcode)
    # is one reading: keep its best occurrence.
    ranked: list[Candidate] = []
    for field_name in dict.fromkeys(c.field for c in candidates):
        best_per_value: dict[str, Candidate] = {}
        for c in sorted((c for c in candidates if c.field == field_name), key=lambda c: (c.anchor is None, c.distance)):
            best_per_value.setdefault(c.value, c)
        for rank, c in enumerate(best_per_value.values()):
            c.rank = 0 if field_name in MULTI_VALUE_FIELDS else rank
            ranked.append(c)
    candidates = ranked

    # Keep every other number seen on the page (one entry per value and source) — never silently dropped.
    assigned = {(c.value, c.source) for c in candidates}
    unassigned, seen = [], set()
    for t in tokens + barcode_tokens:
        value = _digits(t.text)
        if t.negative or len(value) < settings.number_digits[0] or (value, t.source) in assigned or (value, t.source) in seen:
            continue
        seen.add((value, t.source))
        unassigned.append({"value": value, "raw": t.text, "source": t.source, "box": asdict(t.box), "confidence": t.confidence})
    return LocalResult(candidates=candidates, labels=labels, unassigned_numbers=unassigned, form_type=form_type)
