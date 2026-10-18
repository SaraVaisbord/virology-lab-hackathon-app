"""
report_html.py - Generate a human-readable HTML comparison report.
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from backend.compare import AGREE, DISAGREE, LIBRARY_ONLY, AI_ONLY, AMBIGUOUS

STATUS_STYLE = {
    AGREE:        ("✅", "#d4edda", "#155724"),
    DISAGREE:     ("❌", "#f8d7da", "#721c24"),
    LIBRARY_ONLY: ("📚", "#fff3cd", "#856404"),
    AI_ONLY:      ("🤖", "#cce5ff", "#004085"),
    AMBIGUOUS:    ("⚠️",  "#e2e3e5", "#383d41"),
}

STATUS_LABEL = {
    AGREE:        "התאמה",
    DISAGREE:     "אי-התאמה",
    LIBRARY_ONLY: "ספרייה בלבד",
    AI_ONLY:      "AI בלבד",
    AMBIGUOUS:    "לא חד-משמעי",
}


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{n} ({100 * n // total}%)"


def _stat_row(label: str, value: str) -> str:
    return f"<tr><td>{label}</td><td><strong>{value}</strong></td></tr>"


def _comparison_row(c: dict) -> str:
    icon, bg, fg = STATUS_STYLE.get(c["status"], ("?", "#fff", "#000"))
    label = STATUS_LABEL.get(c["status"], c["status"])
    return (
        f'<tr style="background:{bg};color:{fg}">'
        f'<td>{c.get("page") or "—"}</td>'
        f'<td><code>{c.get("library_value") or "—"}</code></td>'
        f'<td>{c.get("library_type") or "—"}</td>'
        f'<td><code>{c.get("ai_value") or "—"}</code></td>'
        f'<td>{c.get("ai_type_guess") or "—"}</td>'
        f'<td>{c.get("ai_confidence") or "—"}</td>'
        f'<td>{icon} {label}</td>'
        f'<td>{c.get("note") or ""}</td>'
        f'</tr>'
    )


def _extra_fields_section(extra: dict) -> str:
    parts = []
    for field_key, label in [
        ("commitment_numbers", "מספרי התחייבות"),
        ("central_numbers", "מספרים מרכזיים"),
        ("sender_organizations", "גורם שולח"),
        ("received_dates", "תאריך קבלה"),
    ]:
        items = extra.get(field_key, [])
        if not items:
            continue
        rows = "".join(
            f"<tr><td>{it.get('page','—')}</td>"
            f"<td><code>{it.get('value','')}</code></td>"
            f"<td>{it.get('confidence','')}</td></tr>"
            for it in items
        )
        parts.append(
            f"<h4>{label}</h4>"
            f"<table><thead><tr><th>עמוד</th><th>ערך</th><th>ביטחון</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    uncertain = extra.get("uncertain_fields", [])
    if uncertain:
        rows = "".join(
            f"<tr><td>{it.get('page','—')}</td>"
            f"<td>{it.get('field','')}</td>"
            f"<td><code>{it.get('raw_value','')}</code></td>"
            f"<td>{it.get('reason','')}</td></tr>"
            for it in uncertain
        )
        parts.append(
            "<h4>שדות לא ודאיים</h4>"
            "<table><thead><tr><th>עמוד</th><th>שדה</th><th>ערך גולמי</th><th>סיבה</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    if extra.get("notes"):
        parts.append(f"<h4>הערות AI</h4><p>{extra['notes']}</p>")
    return "\n".join(parts)


def generate_html(results: list[dict], output_path: str) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    total_docs = len(results)
    total_lib = sum(r["library_found"] for r in results)
    total_ai = sum(r["ai_barcodes_found"] for r in results)
    all_comps = [c for r in results for c in r["barcode_comparisons"]]
    grand = {
        AGREE: sum(1 for c in all_comps if c["status"] == AGREE),
        DISAGREE: sum(1 for c in all_comps if c["status"] == DISAGREE),
        LIBRARY_ONLY: sum(1 for c in all_comps if c["status"] == LIBRARY_ONLY),
        AI_ONLY: sum(1 for c in all_comps if c["status"] == AI_ONLY),
        AMBIGUOUS: sum(1 for c in all_comps if c["status"] == AMBIGUOUS),
    }
    total_comps = len(all_comps)
    model_name = results[0].get("ai_model", "—") if results else "—"

    # ── Per-document sections ────────────────────────────────────────────────
    doc_sections = []
    for r in results:
        fname = Path(r["file"]).name
        s = r["summary"]
        comp_rows = "".join(_comparison_row(c) for c in r["barcode_comparisons"])
        extra_html = _extra_fields_section(r.get("ai_extra_fields", {}))

        doc_sections.append(f"""
<section class="doc-section">
  <h2>📄 {fname}</h2>
  <table class="stats">
    <tr><td>עמודים (ספרייה)</td><td><strong>{r['library_pages']}</strong></td></tr>
    <tr><td>ברקודים שנמצאו ע"י ספרייה</td><td><strong>{r['library_found']}</strong></td></tr>
    <tr><td>עמודים שנותחו ע"י AI</td><td><strong>{r['ai_pages_analyzed']}</strong></td></tr>
    <tr><td>ברקודים שזוהו ע"י AI</td><td><strong>{r['ai_barcodes_found']}</strong></td></tr>
    <tr><td>סה"כ השוואות</td><td><strong>{s['total']}</strong></td></tr>
    <tr><td>✅ התאמות</td><td><strong>{_pct(s['counts'].get(AGREE,0), s['total'])}</strong></td></tr>
    <tr><td>📚 ספרייה בלבד</td><td><strong>{_pct(s['counts'].get(LIBRARY_ONLY,0), s['total'])}</strong></td></tr>
    <tr><td>🤖 AI בלבד</td><td><strong>{_pct(s['counts'].get(AI_ONLY,0), s['total'])}</strong></td></tr>
    <tr><td>⚠️ לא חד-משמעי</td><td><strong>{_pct(s['counts'].get(AMBIGUOUS,0), s['total'])}</strong></td></tr>
  </table>

  <h3>טבלת השוואה מפורטת</h3>
  <div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>עמוד</th>
        <th>ערך ספרייה</th>
        <th>סוג ספרייה</th>
        <th>ערך AI</th>
        <th>סוג AI</th>
        <th>ביטחון AI</th>
        <th>סטטוס</th>
        <th>הערה</th>
      </tr>
    </thead>
    <tbody>{comp_rows}</tbody>
  </table>
  </div>

  <h3>שדות נוספים שחולצו ע"י AI</h3>
  {extra_html if extra_html else "<p>לא חולצו שדות נוספים.</p>"}
</section>
""")

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>דוח השוואה – קריאת ברקודים</title>
  <style>
    body {{ font-family: Arial, sans-serif; direction: rtl; margin: 0; padding: 0;
            background: #f5f5f5; color: #222; }}
    header {{ background: #1a1a2e; color: white; padding: 2rem; }}
    header h1 {{ margin: 0 0 .4rem; font-size: 1.8rem; }}
    header p  {{ margin: 0; opacity: .8; }}
    main {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
    h2 {{ border-bottom: 2px solid #1a1a2e; padding-bottom: .4rem; }}
    h3 {{ color: #1a1a2e; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem;
             font-size: .9rem; }}
    th {{ background: #1a1a2e; color: white; padding: 8px 10px; text-align: right; }}
    td {{ padding: 6px 10px; border: 1px solid #ddd; vertical-align: top; }}
    tr:nth-child(even) td {{ background: #fafafa; }}
    code {{ background: #eee; padding: 1px 4px; border-radius: 3px;
            font-size: .85rem; word-break: break-all; }}
    .stats td:first-child {{ width: 55%; }}
    .table-wrap {{ overflow-x: auto; }}
    .doc-section {{ background: white; border-radius: 8px; padding: 1.5rem;
                    margin-bottom: 2rem; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr));
                     gap: 1rem; margin-bottom: 2rem; }}
    .card {{ background: white; border-radius: 8px; padding: 1.2rem;
             text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
    .card .num {{ font-size: 2.2rem; font-weight: bold; color: #1a1a2e; }}
    .card .lbl {{ font-size: .85rem; color: #555; margin-top: .3rem; }}
    .warning {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
                padding: 1rem; margin-bottom: 1.5rem; }}
    footer {{ text-align: center; padding: 2rem; color: #888; font-size: .8rem; }}
  </style>
</head>
<body>
<header>
  <h1>דוח השוואה – קריאת ברקודים</h1>
  <p>נוצר: {now} &nbsp;|&nbsp; מודל AI: {model_name}</p>
</header>
<main>

<!-- A. Executive Summary -->
<section class="doc-section">
  <h2>א. סיכום מנהלים</h2>
  <p>
    הניסוי השווה שתי גישות לחילוץ ברקודים מטפסי התחייבות רפואיים:
    <strong>ספריית pyzbar</strong> (עיבוד מקומי, ללא שליחת נתונים לחוץ)
    מול <strong>מודל AI חיצוני ({model_name})</strong> שקיבל את ה-PDF ישירות.
  </p>
  <p>
    עובדו <strong>{total_docs} מסמכים</strong>.
    הספרייה מצאה <strong>{total_lib} ברקודים</strong>;
    ה-AI זיהה <strong>{total_ai} ברקודים</strong>.
    מתוך <strong>{total_comps} השוואות</strong>:
    <strong>{grand[AGREE]} התאמות</strong>,
    <strong>{grand[LIBRARY_ONLY]} נמצאו ע"י הספרייה בלבד</strong>,
    <strong>{grand[AI_ONLY]} נמצאו ע"י AI בלבד</strong>.
  </p>
  <div class="warning">
    ⚠️ <strong>שים לב:</strong> מסמכים נשלחו לשרתי Anthropic לצורך ניתוח.
    יש לבחון את מדיניות הפרטיות של Anthropic לפני עיבוד רשומות רפואיות אמיתיות.
    אין אימות ground-truth – לא ניתן לקבוע דיוק מוחלט.
  </div>
</section>

<!-- B. Results Overview -->
<section class="doc-section">
  <h2>ב. סקירת תוצאות</h2>
  <div class="summary-grid">
    <div class="card"><div class="num">{total_docs}</div><div class="lbl">מסמכים</div></div>
    <div class="card"><div class="num">{total_lib}</div><div class="lbl">ברקודים (ספרייה)</div></div>
    <div class="card"><div class="num">{total_ai}</div><div class="lbl">ברקודים (AI)</div></div>
    <div class="card"><div class="num">{grand[AGREE]}</div><div class="lbl">✅ התאמות</div></div>
    <div class="card"><div class="num">{grand[LIBRARY_ONLY]}</div><div class="lbl">📚 ספרייה בלבד</div></div>
    <div class="card"><div class="num">{grand[AI_ONLY]}</div><div class="lbl">🤖 AI בלבד</div></div>
    <div class="card"><div class="num">{grand[AMBIGUOUS]}</div><div class="lbl">⚠️ לא חד-משמעי</div></div>
  </div>
  <table class="stats">
    {_stat_row("סה&quot;כ השוואות", str(total_comps))}
    {_stat_row("✅ התאמות", _pct(grand[AGREE], total_comps))}
    {_stat_row("📚 ספרייה בלבד", _pct(grand[LIBRARY_ONLY], total_comps))}
    {_stat_row("🤖 AI בלבד", _pct(grand[AI_ONLY], total_comps))}
    {_stat_row("⚠️ לא חד-משמעי", _pct(grand[AMBIGUOUS], total_comps))}
  </table>
  <p><em>המכנה לכל אחוז הוא סה"כ ההשוואות ({total_comps}).</em></p>
</section>

<!-- C+D. Per-document details -->
<section class="doc-section">
  <h2>ג–ד. פירוט לפי מסמך</h2>
</section>
{"".join(doc_sections)}

<!-- E. Conclusions -->
<section class="doc-section">
  <h2>ה. מסקנות והמלצות</h2>
  <ul>
    <li><strong>ספריית pyzbar</strong> – מהירה, מקומית, ומדויקת לברקודים ברורים. מחזירה מיקום מדויק בתמונה.</li>
    <li><strong>AI</strong> – מסוגל לחלץ שדות טקסטואליים (מספרי התחייבות, שמות, תאריכים) שהספרייה אינה מטפלת בהם כלל. לברקודים עצמם – הביצועים תלויים באיכות הסריקה.</li>
    <li>ברקודים שנמצאו ע"י הספרייה בלבד דורשים בדיקה: ייתכן שה-AI לא זיהה אותם כברקודים, או שהם קטנים/מטושטשים.</li>
    <li>ברקודים שנמצאו ע"י AI בלבד דורשים אימות ידני – ייתכן שמדובר בזיהוי שגוי.</li>
    <li><strong>אין ground-truth</strong> – לא ניתן לקבוע איזו גישה "נכונה" יותר ללא אימות ידני.</li>
    <li>שמירת שתי הגישות מומלצת: הספרייה לברקודים, AI לשדות טקסטואליים.</li>
  </ul>
</section>

<!-- F. Methodology -->
<section class="doc-section">
  <h2>ו. מתודולוגיה ומגבלות</h2>
  <table class="stats">
    {_stat_row("ספק AI", "Anthropic")}
    {_stat_row("מודל", model_name)}
    {_stat_row("ספריית ברקודים", "pyzbar + pymupdf")}
    {_stat_row("מסמכים שנבדקו", str(total_docs))}
    {_stat_row("כלל ההשוואה", "התאמה לפי (עמוד + ערך מנורמל)")}
    {_stat_row("נורמליזציה", "trim whitespace + uppercase; אין הסרת אפסים מובילים")}
    {_stat_row("ground-truth", "לא קיים – אין חישוב דיוק")}
  </table>
  <p>
    <strong>מגבלות:</strong>
    ה-AI עשוי לפספס ברקודים קטנים או מוטים.
    הספרייה אינה מחלצת טקסט חופשי.
    מסמכים נשלחו לשרתי Anthropic – יש לבחון את מדיניות הפרטיות לפני שימוש בנתונים אמיתיים.
  </p>
</section>

</main>
<footer>נוצר אוטומטית ע"י run_experiment.py &nbsp;|&nbsp; {now}</footer>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path
