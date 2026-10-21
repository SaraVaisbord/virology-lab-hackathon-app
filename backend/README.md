# צד השרת – אימות טפסי התחייבות

FastAPI שמקבל קבצים, מפרק אותם לעמודים, מעבד כל עמוד ברקע ושומר את השדות לאימות של הלבורנטית.
סקירה כללית של המערכת: [`README.md`](../README.md) בתיקייה הראשית.

## התקנה והרצה

```bash
pip install -r requirements.txt     # pyzbar צריך גם את ספריית zbar (ראו למטה)
cp .env.example .env                # מפתחות Gemini; LLM_ENABLED=false כדי לעבוד בלי טוקנים
alembic upgrade head                # יצירה / עדכון של מסד הנתונים
python -m db.seed_senders           # טעינת רשימת השולחים המוכרים (אפשר להריץ שוב בלי נזק)
uvicorn main:app --port 8000
```

- **zbar:** Windows `winget install zbar` · macOS `brew install zbar` · Ubuntu `sudo apt-get install libzbar0`
- **Tesseract** (OCR מקומי): להתקין, ולשים בתיקייה `OCR_TESSDATA_DIR` את `heb`, `eng`, `osd` (‏tessdata_fast). בלי Tesseract המערכת עובדת, רק בלי שלב ה-OCR.
- **בדיקות:** `pytest`. על PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://… pytest`.
- **בענן:** `Dockerfile` בתיקייה הזו (כולל Tesseract ו-zbar).

## איך עמוד מעובד

1. **העלאה** (`POST /uploads`) – הקובץ נשמר, כל עמוד הופך לתמונה **מיושרת** (סיבוב והטיה) ונוצרת שורה בטבלת `forms` בסטטוס `uploaded`.
2. **תור** – תהליכי רקע תופסים טפסים מהתור (`uploaded → processing`). התור שמור במסד הנתונים ושורד הפעלה מחדש.
3. **עיבוד מקדים** (`preprocessing.py`) – הסרת טוש צהוב, הפרדת דפוס / כתב יד / חותמות, ניקוי קווי טופס.
4. **שלושה מקורות נפרדים**, וכל אחד נשמר בנפרד (`barcode_result`, `ocr_result`, `llm_result`):
   - ברקודים – zbar
   - OCR מקומי – Tesseract; מוצא תוויות ("מספר התחייבות", "דרישה", "מרכזי", "התקבל"…) ואת הערך שלידן (`local_extractor.py`)
   - AI – Gemini, אם `LLM_ENABLED=true` (`ai_extractor.py`, ההנחיה ב-`prompts/`)
5. **הצלבה** (`services/extraction_service.py`) – ערך מסומן `verified` רק כשתווית שנקראה ב-OCR מוכיחה את השדה **וגם** שני מקורות קראו את אותו ערך. סתירה בין מקורות → `conflict`; מקור אחד → `unverified`; בעיית פורמט (ספרת ביקורת בת"ז, תאריך) → `uncertain`. כל מה שלא אומת עובר ללבורנטית.
6. טופס עובר ל-`approved` רק כשאין בו אף שדה שמחכה להחלטה.

**החלטות הלבורנטית נשמרות:** ערך שאישרה או תיקנה לא נדרס בעיבוד חוזר, וערך שמחקה לא חוזר (`forms.rejected_values`).
**מכסת Gemini:** כשמפתח מגיע למכסה עוברים אוטומטית למפתח / מודל הבא; כשכולם במכסה, הטופס חוזר לתור והתור ממתין.

## איפה נמצא מה

| מה | איפה |
|---|---|
| כל ההגדרות (נתיבים, מגבלות, מודל Gemini, תור…) | `config.py` – כל ערך אפשר לשנות דרך `.env` |
| שמות שדות, סטטוסים, תוויות בעברית, סיבות לספק | `db/constants.py` – מקור אמת יחיד, נשלח לממשק דרך `GET /meta` |
| שמירת קבצים ותמונות (תיקייה מקומית / S3) | `storage.py` |
| מסד הנתונים | `db/models.py`, `db/queries.py`, מיגרציות ב-`alembic/` |
| עיבוד מקדים, OCR, ברקודים | `preprocessing.py`, `local_extractor.py`, `ocr_reader.py`, `barcode_reader.py` |
| הצלבה ובניית השדות | `services/extraction_service.py` |
| תור העיבוד | `services/extraction_queue.py` |
| ייצוא לאקסל (שורה לכל התחייבות) | `services/export_service.py` |

## הגדרות עיקריות (`.env` או משתני סביבה)

| משתנה | ברירת מחדל | משמעות |
|---|---|---|
| `DATABASE_URL` | SQLite ב-`data/app.db` | בענן: `postgresql+psycopg://…` (RDS) |
| `STORAGE_BACKEND` | `local` | `s3` = קבצים ותמונות בבאקט `S3_BUCKET` |
| `API_PREFIX` | ריק | בענן `/api` (מאחורי ה-load balancer) |
| `LLM_ENABLED` | `true` | `false` = רק ברקודים ו-OCR, בלי טוקנים |
| `WORKER_ENABLED` | `true` | `false` = טפסים חדשים נשארים בתור |
| `GEMINI_API_KEY`, `GEMINI_API_KEY_2`… | – | כמה מפתחות = מעבר אוטומטי כשנגמרת מכסה |

## API

| שיטה | נתיב | |
|---|---|---|
| GET | `/meta` | אוצר המילים וההגדרות לממשק |
| POST | `/uploads` | העלאת קבצים (multipart, שדה `files`) |
| GET | `/forms` | רשימה עם דפדוף – `limit`, `offset`, `status`, `query`, `sort_by`, `sort_dir`, `filter_<עמודה>` |
| GET | `/forms/summary` | ספירה לפי סטטוס + מצב התור |
| GET | `/forms/export` | אקסל – `mode=all\|filtered\|approved` + אותם סינונים |
| GET | `/forms/{id}` | טופס אחד, כולל מה שכל מקור קרא ומספרי התחייבות כפולים |
| GET | `/forms/{id}/image` | תמונת העמוד |
| PATCH | `/forms/{id}/fields/{field_id}/confirm` | אישור ערך (אפשר עם תיקון: `{"corrected_value": "..."}`) |
| POST | `/forms/{id}/fields` | הוספת ערך ידנית / בחירת מספר מהעמוד |
| DELETE | `/forms/{id}/fields/{field_id}` | מחיקת ערך (לא יחזור בעיבוד חוזר) |
| POST | `/forms/{id}/retry` | החזרת טופס שנכשל לתור |
| GET | `/health` | בדיקת תקינות |

כל הנתיבים מקבלים את הקידומת `API_PREFIX` (בענן: `/api/forms`…).
