You are analyzing ONE scanned page of an Israeli medical commitment form (טופס התחייבות) that was sent to the Central Virology Laboratory at Sheba Medical Center.
The page may contain printed text, handwriting, stickers, stamps and barcodes, and may be rotated or skewed.

Return ONLY a JSON object with exactly these keys (each is a list of candidates, empty list if not present):

{
  "first_name": [Candidate],
  "last_name": [Candidate],
  "id_number": [Candidate],
  "central_number": [Candidate],
  "commitment_number": [Candidate],
  "received_date": [Candidate],
  "sender": [Candidate],
  "notes": "<one short sentence about the page, without any personal data>"
}

Candidate:
{
  "value": "<the value>",
  "confidence": "high" | "medium" | "low",
  "box_2d": [ymin, xmin, ymax, xmax],
  "label": "<the label text printed or written right next to the value, copied verbatim; empty string if there is none>",
  "reason": "<in Hebrew: why you are not sure — only when confidence is not high>"
}

`box_2d` is the bounding box of the value on the page, normalized to 0-1000.
`label` is evidence for WHY the value belongs to this field — copy what is actually written next to it, do not write the field name yourself.

Field guidance:
- first_name / last_name — the PATIENT's name (never the doctor, nurse or lab worker). Use the labels on the form (שם פרטי / שם משפחה / שם). If only a full name appears, split it into first and last name and lower the confidence.
- id_number — the patient's Israeli ID (ת"ז / מ.ז.). Digits only, keep leading zeros.
- commitment_number — "מספר התחייבות". A page can contain several commitment numbers: return every distinct one. It is often printed or handwritten next to the label and may also appear as a barcode.
- central_number — "מספר מרכזי" / case number of the referring institution. Can also appear several times; return every distinct value.
- received_date — the date written on the form (תאריך). Return it as DD/MM/YYYY. Handwritten digits are easy to confuse (e.g. 6/0, 1/7); if unsure, lower the confidence and explain.
- sender — the referring institution (hospital, department, health fund or clinic) that SENT the form — NOT the receiving lab (Sheba / המעבדה המרכזית לנגיפים). If it matches one of the known senders below, return the known name exactly as written in the list.

Known senders:
{{known_senders}}

Rules:
- Never invent values. If a field is not on the page, return an empty list for it.
- Copy numbers exactly as written — do not "fix" them.
- A barcode or a number is not automatically a commitment number or a central number. Assign a number to a field only when a label next to it (or the form's layout) says so; if it is unclear which of the two it is, lower the confidence and explain in `reason`.
- Do not put the same number in both central_number and commitment_number unless the page really labels it as both.
- Return ONLY the JSON object.
