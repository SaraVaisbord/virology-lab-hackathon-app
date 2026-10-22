"""Domain vocabulary — the single source of truth for field names, statuses and their Hebrew labels.

The frontend receives these through GET /meta, so nothing here should be duplicated in the UI.
"""

# Ordered: this is also the display/export column order.
FIELD_LABELS = {
    "first_name": "שם פרטי",
    "last_name": "שם משפחה",
    "id_number": 'ת"ז',
    "central_number": "מספר מרכזי",
    "commitment_number": "מספר התחייבות",
    "received_date": "תאריך קבלה",
    "sender": "גורם שולח",
}
FIELDS = tuple(FIELD_LABELS)

# What kind of value each field holds: how values are validated locally, and which numbers found on the page are
# offered to the lab worker as options for the field (numbers for number/id fields, dates for date fields).
FIELD_KINDS = {
    "first_name": "text",
    "last_name": "text",
    "id_number": "id",
    "central_number": "number",
    "commitment_number": "number",
    "received_date": "date",
    "sender": "text",
}
# A date as written on the forms: D/M/YY .. DD.MM.YYYY (separators / . -). Also sent to the frontend via /meta.
DATE_PATTERN = r"(?<!\d)(\d{1,2})[./\-](\d{1,2})[./\-](\d{2}|\d{4})(?!\d)"

# LLM page inventory (all_numbers): how each number appears on the page, and the "not assigned" marker.
INVENTORY_KINDS = ("barcode", "sticker", "printed", "handwritten")
UNASSIGNED = "none"

# The export has one row per commitment: the commitment number is the row key (the lab's definition). The same
# number on two forms is flagged for the lab worker (usually one form uploaded twice).
ROW_KEY_FIELD = "commitment_number"

# Fields that may legitimately hold several values on one page.
MULTI_VALUE_FIELDS = frozenset({"central_number", "commitment_number"})

# Fields whose values may also be printed as a barcode, so the value READING can be cross-checked locally.
# A barcode carries no label, so a match never proves which field the number belongs to.
BARCODE_FIELDS = frozenset({"central_number", "commitment_number", "id_number"})

# Number fields that look alike (both are plain digit strings) — assigning a number to one of them needs
# evidence from a label next to it, not just the number itself.
AMBIGUOUS_NUMBER_FIELDS = frozenset({"central_number", "commitment_number"})

# Words that, when they appear in the label next to a value, indicate which field it belongs to.
# Commitment number = the row key of the export; also written as "דרישה". Central number = the LAB's internal
# number given on receipt (sticker "מרכזי"), never a number of the health fund or the referring institution.
FIELD_LABEL_KEYWORDS = {
    "commitment_number": ("התחייבות", "דרישה"),
    "central_number": ("מרכזי",),
    "id_number": ('ת"ז', "ת.ז", "מ.ז", "זהות"),
}

# Health-fund form types recognised from a word printed on the page. Only funds whose name can't be mistaken for
# an ordinary word are listed ("כללית" also means "general", e.g. "רפואה כללית").
FORM_TYPE_MARKERS = {"leumit": ("לאומית",)}
# "דגימה" (sample) labels the commitment number only where the sample number IS the commitment: on Leumit forms,
# and on any page that says so itself (Rambam: "מספר הדגימה מהווה מספר התחייבות"; Clalit: "מס' הדגימה משמש גם
# כמס' אסמכתא להתחייבות"). Elsewhere "מספר דגימה" is a test number, NOT the commitment.
SAMPLE_LABEL = "דגימה"
SAMPLE_IS_COMMITMENT_FORM_TYPES = frozenset({"leumit"})
# Both words on one printed line = the page's own declaration that its sample number is the commitment number.
SAMPLE_IS_COMMITMENT_LINE = ("דגימה", "התחייבות")


def label_keywords(sample_is_commitment: bool = False) -> dict[str, tuple[str, ...]]:
    """FIELD_LABEL_KEYWORDS, plus "דגימה" for the commitment number on pages where the sample number is the commitment."""
    extra = {"commitment_number": (SAMPLE_LABEL,)} if sample_is_commitment else {}
    return {name: words + extra.get(name, ()) for name, words in FIELD_LABEL_KEYWORDS.items()}


# Label lexicon for the local (OCR) extractor. A printed line is a label for a field when it contains one of
# `keywords` and none of `exclude_if_line_has` (e.g. the title "טופס התחייבות" is not a commitment-number label).
# `requires_one_of`: at least one of these words must be on the line too (e.g. "מספר התחייבות", not just "התחייבות").
LOCAL_LABEL_LEXICON = {
    "commitment_number": {
        "keywords": ("התחייבות", "ההתחייבות", "דרישה"),
        # "מספר התחייבות" / "מס' דרישה", or a form title "טופס התחייבות ... מס' 58153" — all carry a number word
        # (a heading such as "דרישה לבדיקה" doesn't). Form-type labels (Leumit "דגימה") don't need one.
        "requires_one_of": ("מספר", "מס'", "מס", "מס׳"),
        # ...but not instructions such as "נא לציין את מספר ההתחייבות" or payment notes.
        "exclude_if_line_has": ("לציין", "תשלום", "לתשלום"),
    },
    "central_number": {"keywords": ("מרכזי",), "requires_one_of": (), "exclude_if_line_has": ()},
    "id_number": {"keywords": ('ת"ז', "ת.ז", "מ.ז", "זהות"), "requires_one_of": (), "exclude_if_line_has": ()},
    "received_date": {
        # A page has many dates; "ת.קבלה" / "קבלה" / "התקבל" (strong) say "received", plain "תאריך" (weak) doesn't.
        "keywords": ("תאריך", "התקבל", "נתקבל", "קבלה", "ת.קבלה"),
        "strong_keywords": ("התקבל", "נתקבל", "קבלה", "ת.קבלה"),
        "requires_one_of": (),
        "exclude_if_line_has": ("לידה", "שחרור", "הדגימה", "לשחרור"),
    },
}
# Hebrew one-letter prefixes (the/and/in/to/from/that/as) that may be glued to a label word: "ההתחייבות", "מתאריך".
HEBREW_PREFIXES = ("ה", "ו", "ב", "ל", "מ", "ש", "כ")
# Numbers on a line with one of these words are never form values (catalog no., phone, fax, zip, birth date).
# Numbers that are never form values — phone / mobile / fax, zip, P.O. box, address, catalog no., birth date,
# department, hospital, doctor's licence (מ.ר). The number right after such a word is dropped everywhere: OCR results,
# the AI's page inventory and the options shown to the lab worker.
IRRELEVANT_NUMBER_LABELS = ('מק"ט', "מק״ט", "טל", "טלפון", "נייד", "פלאפון", "פקס", "מיקוד", "ת.ד", "כתובת", "לידה",
                            "ח.לידה", "מחלקה", "מחלקת", "חולים", 'ביה"ח', 'בי"ח', "רישיון", "מ.ר")
# Phone numbers by their shape, with or without a label: 03-5303030, 050-8259728, 0527736881, +972..., *3833.
# (Undashed 9-digit numbers are NOT treated as phones — Israeli IDs look the same.)
PHONE_PATTERN = r"^\+?972|^0\d{1,2}-\d{3}-?\d{4}$|^0[57]\d{8}$|^\*\d{4}$"

FORM_STATUS_LABELS = {
    "uploaded": "בתור לעיבוד",
    "processing": "בעיבוד",
    "extracted": "ממתין לאימות",
    "approved": "אושר",
    "failed": "נכשל",
}
FORM_STATUSES = frozenset(FORM_STATUS_LABELS)
# Forms that are still waiting for (or inside) the extraction queue.
PENDING_FORM_STATUSES = frozenset({"uploaded", "processing"})

FIELD_STATUS_LABELS = {
    "conflict": "סתירה בין מקורות",
    "uncertain": "לא ודאי",
    "unverified": "לא מאומת",
    "not_found": "לא נמצא",
    "verified": "אומת משני מקורות",
    "confirmed": "אושר",
}
FIELD_STATUSES = frozenset(FIELD_STATUS_LABELS)
# Field statuses that still need a human decision.
REVIEW_FIELD_STATUSES = frozenset({"conflict", "uncertain", "unverified", "not_found"})

# How the sources relate for one field (stored in the field's evidence).
AGREEMENT_LABELS = {
    "agree": "המקורות מסכימים על הערך",
    "conflict": "המקורות סותרים",
    "insufficient": "אין מספיק ראיות ממקור נוסף",
}

# Extraction sources (the page is read independently by each one).
SOURCE_LABELS = {
    "llm": "AI (Gemini)",
    "barcode": "ברקוד",
    "ocr": "OCR",
}
# Per-source run status, stored with each source's result.
SOURCE_STATUS_LABELS = {
    "ok": "הורץ",
    "error": "נכשל",
    "unavailable": "לא זמין",
}

CONFIDENCE_LABELS = {"high": "ביטחון גבוה", "medium": "ביטחון בינוני", "low": "ביטחון נמוך"}
CONFIDENCE_LEVELS = frozenset(CONFIDENCE_LABELS)

# How a barcode relates to the value the LLM read.
BARCODE_MATCH_LABELS = {"exact": "זהה לקריאת ה-AI", "near": "שונה בתו אחד מקריאת ה-AI"}

FORM_TYPES = frozenset({"clalit", "maccabi", "meuhedet", "leumit", "hospital", "other"})

SENDER_KINDS = frozenset({"health_fund", "hospital", "lab", "government", "military", "other"})

# Correction history (field_events): what the lab worker did to a field and what kind of change it was — the
# material for finding recurring extraction mistakes. Only these classifications are stored, never the values
# (they may identify the patient; the values themselves stay in extracted_fields).
FIELD_EVENT_ACTION_LABELS = {
    "confirm": "אושר כפי שהוא",
    "edit": "תוקן",
    "replace": "הוחלף בערך מהעמוד",
    "add": "נוסף ערך",
    "delete": "נמחק",
}
FIELD_EVENT_ACTIONS = frozenset(FIELD_EVENT_ACTION_LABELS)
CHANGE_KIND_LABELS = {
    "none": "ללא שינוי",
    "format_only": "שינוי כתיב בלבד",
    "typo": "תווים בודדים שונו",
    "transposition": "אותן ספרות בסדר אחר",
    "day_month_swap": "היום והחודש בתאריך הוחלפו",
    "wrong_field": "הערך שייך לשדה אחר בטופס",
    "different_value": "ערך אחר",
    "filled_missing": "הושלם ערך חסר",
    "removed": "הערך נמחק",
    "restored": "הוחזר הערך שהמערכת קראה",
}
CHANGE_KINDS = frozenset(CHANGE_KIND_LABELS)
# Where the value a correction started from came from: the extraction (not yet decided), the extraction as the lab
# worker approved it, or a value she set herself (typed, picked from the page, or emptied by deleting it).
VALUE_ORIGINS = frozenset({"machine", "machine_confirmed", "manual"})
# Up to this many changed characters (after normalizing) is a "typo"; more is a different value.
TYPO_MAX_CHANGED_CHARS = 2

# Human-readable reasons attached to fields that need review. {placeholders} are filled by the extraction service.
REASONS = {
    "barcode_near_match": "ברקוד בעמוד שונה בתו אחד מקריאת ה-AI: {barcode}",
    "claimed_by_other_field": "אותו מספר זוהה גם כ{other} – לא ברור לאיזה שדה הוא שייך",
    "label_points_elsewhere": "התווית ליד הערך ('{label}') מתאימה ל{other}",
    "assignment_llm_only": "הערך נקרא בכמה מקורות, אך השיוך לשדה מבוסס על ה-AI בלבד – לא נמצאה תווית מתאימה ליד הערך ב-OCR",
    "single_source": "הערך נקרא רק על ידי ה-AI – אין מקור נוסף שמאשר אותו",
    "local_only": "הערך נמצא ליד התווית בסריקה המקומית בלבד – אין מקור נוסף שמאשר את הקריאה",
    "ocr_label_elsewhere": "התווית שזוהתה ב-OCR ליד אותו מספר מתאימה ל{other}",
    "invalid_id_checksum": 'ספרת הביקורת של מספר ת"ז אינה תקינה',
    "invalid_date": "פורמט התאריך לא זוהה",
    "implausible_date": "התאריך רחוק מהתאריך הנוכחי או עתידי – ייתכן שגיאת קריאה בספרות",
    "unknown_sender": "הגורם השולח לא נמצא ברשימת השולחים המוכרים",
    "low_confidence": "רמת ביטחון נמוכה בזיהוי הערך",
    "not_found": "השדה לא נמצא בטופס",
    "rejected_by_worker": "הערך שזוהה נמחק על ידי הלבורנטית – יש להזין ערך נכון או לאשר שהשדה ריק",
    "received_dates_differ": "מתחת למספרים המרכזיים רשומים תאריכים שונים ({dates}) – יש לבחור את תאריך הקבלה",
}

# The received date is the one written (or stamped "התקבל") right under the central number; a date found there is
# labelled with this text (the central number's value filled in).
RECEIVED_DATE_ANCHOR_LABEL = "מתחת למספר המרכזי {value}"

# Why OCR evidence is missing (no OCR engine is installed in this deployment).
OCR_UNAVAILABLE_REASON = "לא מותקן מנוע OCR – לא ניתן לאמת תוויות ומיקומים מטקסט העמוד"

# Supported upload types: detected by magic bytes on the server, pre-checked by MIME/extension in the browser.
UPLOAD_TYPES = {
    "pdf": {"magic": b"%PDF", "mime": "application/pdf", "extensions": (".pdf",)},
    "png": {"magic": b"\x89PNG\r\n\x1a\n", "mime": "image/png", "extensions": (".png",)},
    "jpeg": {"magic": b"\xff\xd8\xff", "mime": "image/jpeg", "extensions": (".jpg", ".jpeg")},
}

# User-facing extraction failure messages (technical details go to the server log only).
EXTRACTION_ERRORS = {
    "image_missing": "קובץ התמונה של העמוד לא נמצא",
    "timeout": "Gemini לא הגיב בזמן – אפשר לנסות שוב",
    "model": "שגיאה בקבלת תשובה מ-Gemini – אפשר לנסות שוב",
    "config": "מפתח Gemini לא הוגדר בשרת",
    "quota": "Gemini לא זמין כרגע (מכסה או עומס) – הטופס הוחזר לתור",
    "barcode": "סריקת הברקודים נכשלה",
    "ocr": "הסריקה המקומית (OCR) נכשלה",
    "unexpected": "שגיאה לא צפויה בעיבוד הטופס",
}

QUEUE_PAUSE_REASON_LABELS = {
    "quota": "מכסת הבקשות ל-Gemini נוצלה בכל המפתחות – העיבוד יתחדש אוטומטית",
    "busy": "כל המודלים של Gemini עמוסים כרגע – ניסיון חוזר אוטומטי בקרוב",
    "disabled": "החילוץ האוטומטי מושבת בשרת (WORKER_ENABLED=false) – טפסים חדשים ממתינים בתור",
}

EXPORT_MODE_LABELS = {
    "all": "ייצא הכל",
    "filtered": "ייצא לפי הסינון הנוכחי",
    "approved": "ייצא מאושרים בלבד",
}

# Export-only columns (after the field columns).
EXPORT_COLUMN_LABELS = {"duplicate_of": "ההתחייבות מופיעה גם ב"}

# Extra (non-field) table/export columns.
FORM_COLUMN_LABELS = {
    "id": "מזהה",
    "source_file": "שם קובץ",
    "page_number": "עמוד",
    "status": "סטטוס",
    "uploaded_at": "תאריך העלאה",
}
