You are analyzing ONE scanned page of an Israeli medical commitment form (טופס התחייבות) that was sent to the Central Virology Laboratory at Sheba Medical Center.
The page may contain printed text, handwriting, several stickers, stamps and several barcodes, and may be rotated or skewed.

Work in two steps.

STEP 1 — INVENTORY (do this first, be exhaustive)
Scan the WHOLE page systematically: top to bottom, right to left, including stickers, stamps, margins, corners and the area around every barcode.
List in `all_numbers` EVERY number of 4 or more digits you can see — printed, handwritten, on stickers, and the human-readable number printed under/next to EVERY barcode — each distinct value once.
Include numbers even when you do not know what they are; set `assigned_to` to "none" for those.
Pages very often carry SEVERAL stickers and barcodes (e.g. a referral sticker, a commitment-number sticker, the lab's "מרכזי" sticker). Do not stop after the first one.

STEP 2 — ASSIGN
Fill the fields from the inventory. Every value you put in a field must also appear in `all_numbers` (for numbers).

Return ONLY a JSON object with exactly these keys:

{
  "all_numbers": [Number],
  "form_type": {{form_types}},
  "first_name": [Candidate],
  "last_name": [Candidate],
  "id_number": [Candidate],
  "central_number": [Candidate],
  "commitment_number": [Candidate],
  "received_date": [Candidate],
  "sender": [Candidate],
  "notes": "<one short sentence about the page, without any personal data>"
}

Number (inventory item):
{
  "value": "<digits exactly as written>",
  "kind": "barcode" | "sticker" | "printed" | "handwritten",
  "label": "<the label text right next to it, copied verbatim; empty string if none>",
  "assigned_to": "<one of the field names above, or none>",
  "box_2d": [ymin, xmin, ymax, xmax]
}

Candidate (field value):
{
  "value": "<the value>",
  "confidence": "high" | "medium" | "low",
  "box_2d": [ymin, xmin, ymax, xmax],
  "label": "<the label text printed or written right next to the value, copied verbatim; empty string if there is none>",
  "reason": "<in Hebrew: why you are not sure — only when confidence is not high>"
}

`box_2d` is the bounding box of the value on the page, normalized to 0-1000.
`label` is evidence for WHY the value belongs to this field — copy what is actually written next to it, do not write the field name yourself.

`form_type` — whose form this is: "leumit" = לאומית, "clalit" = כללית, "maccabi" = מכבי, "meuhedet" = מאוחדת, "hospital" = a hospital's own form; "other" when you cannot tell.

Field guidance:
- first_name / last_name — the PATIENT's name (never the doctor, nurse or lab worker). Use the labels on the form (שם פרטי / שם משפחה / שם). If only a full name appears, split it into first and last name and lower the confidence.
- id_number — the patient's Israeli ID (ת"ז / מ.ז.). Digits only, keep leading zeros.
- commitment_number — the health fund's commitment (התחייבות) number; it is the key of the record. It is labelled "מספר התחייבות", sometimes "דרישה" / "מספר דרישה", and on Leumit (לאומית) forms "דגימה" / "מספר דגימה". This is a LIST: the fund issues one commitment per approved item, so one form may carry several — return EVERY distinct commitment number on the page (printed, handwritten, or on a sticker/barcode labelled as such). Other test, referral or order numbers printed on the form are NOT commitment numbers. "דגימה" means a commitment number ONLY on Leumit forms.
- central_number — the CENTRAL LAB's own internal number, given to the sample when the lab receives it (NOT a number of the health fund or of the referring institution, and not a "מקרה" case number). It is on a sticker labelled "מרכזי", or handwritten as "מספר מרכזי …"; right under it there is usually a "התקבל" stamp or a handwritten received date. Also a LIST: one sample may have several central numbers (several tubes) — return EVERY distinct value.
- received_date — the date the lab RECEIVED the sample: the date stamped "התקבל" or handwritten right UNDER the central number. Only when there is none, use a date labelled "ת.קבלה" / "תאריך קבלה" / "התקבל". Not a birth date, discharge date, sample date or the form's issue date. Return it as DD/MM/YYYY. If different central numbers have different dates under them, return EACH of those dates as a candidate (lower the confidence) — the lab worker chooses. Handwritten digits are easy to confuse (e.g. 6/0, 1/7); if unsure, lower the confidence and explain.
- sender — the referring institution (hospital, department, health fund or clinic) that SENT the form — NOT the receiving lab (Sheba / המעבדה המרכזית לנגיפים). If it matches one of the known senders below, return the known name exactly as written in the list.

Known senders:
{{known_senders}}

Rules:
- Never invent values. If a field is not on the page, return an empty list for it.
- Copy numbers exactly as written — do not "fix" them.
- A barcode or a number is not automatically a commitment number or a central number. Assign it to a field only when a label next to it (or the form's layout) says so. If you cannot tell which of the two it is, keep it in `all_numbers` with assigned_to "none" instead of guessing.
- Do not put the same number in both central_number and commitment_number unless the page really labels it as both.
- A number labelled "מקרה" (case number) is neither a central number nor a commitment number: keep it in `all_numbers` with assigned_to "none".
- Numbers that are clearly not form values (phone, fax, zip code, catalog number "מק"ט", dates of birth) go to `all_numbers` with assigned_to "none".
- Return ONLY the JSON object.
