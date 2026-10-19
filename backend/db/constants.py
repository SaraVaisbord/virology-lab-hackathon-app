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

# LLM page inventory (all_numbers): how each number appears on the page, and the "not assigned" marker.
INVENTORY_KINDS = ("barcode", "sticker", "printed", "handwritten")
UNASSIGNED = "none"

# Fields that may legitimately hold several values on one page.
MULTI_VALUE_FIELDS = frozenset({"central_number", "commitment_number"})

# Fields whose values may also be printed as a barcode, so the value READING can be cross-checked locally.
# A barcode carries no label, so a match never proves which field the number belongs to.
BARCODE_FIELDS = frozenset({"central_number", "commitment_number", "id_number"})

# Number fields that look alike (both are plain digit strings) — assigning a number to one of them needs
# evidence from a label next to it, not just the number itself.
AMBIGUOUS_NUMBER_FIELDS = frozenset({"central_number", "commitment_number"})

# Words that, when they appear in the label next to a value, indicate which field it belongs to.
FIELD_LABEL_KEYWORDS = {
    "commitment_number": ("התחייבות",),
    "central_number": ("מרכזי", "מקרה"),
    "id_number": ('ת"ז', "ת.ז", "מ.ז", "זהות"),
}

# Label lexicon for the local (OCR) extractor. A printed line is a label for a field when it contains one of
# `keywords` and none of `exclude_if_line_has` (e.g. the title "טופס התחייבות" is not a commitment-number label).
# `requires_one_of`: at least one of these words must be on the line too (e.g. "מספר התחייבות", not just "התחייבות").
LOCAL_LABEL_LEXICON = {
    "commitment_number": {
        "keywords": ("התחייבות", "ההתחייבות"),
        # "מספר התחייבות", or a form title "טופס התחייבות ... מס' 58153" — both carry a number word.
        "requires_one_of": ("מספר", "מס'", "מס", "מס׳"),
        # ...but not instructions such as "נא לציין את מספר ההתחייבות" or payment notes.
        "exclude_if_line_has": ("לציין", "תשלום", "לתשלום"),
    },
    "central_number": {"keywords": ("מקרה", "מרכזי"), "requires_one_of": (), "exclude_if_line_has": ()},
    "id_number": {"keywords": ('ת"ז', "ת.ז", "מ.ז", "זהות"), "requires_one_of": (), "exclude_if_line_has": ()},
    "received_date": {
        # A page has many dates; "ת.קבלה" / "קבלה" / "התקבל" (strong) say "received", plain "תאריך" (weak) doesn't.
        "keywords": ("תאריך", "התקבל", "קבלה", "ת.קבלה"),
        "strong_keywords": ("התקבל", "קבלה", "ת.קבלה"),
        "requires_one_of": (),
        "exclude_if_line_has": ("לידה", "שחרור", "הדגימה", "לשחרור"),
    },
}
# Hebrew one-letter prefixes (the/and/in/to/from/that/as) that may be glued to a label word: "ההתחייבות", "מתאריך".
HEBREW_PREFIXES = ("ה", "ו", "ב", "ל", "מ", "ש", "כ")
# Numbers on a line with one of these words are never form values (catalog no., phone, fax, zip, birth date).
LOCAL_NEGATIVE_LABELS = ('מק"ט', "מק״ט", "טל", "טל'", "טלפון", "פקס", "מיקוד", "לידה", "ח.לידה", "ת.ד")

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
}

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

# Extra (non-field) table/export columns.
FORM_COLUMN_LABELS = {
    "id": "מזהה",
    "source_file": "שם קובץ",
    "page_number": "עמוד",
    "status": "סטטוס",
    "uploaded_at": "תאריך העלאה",
}
