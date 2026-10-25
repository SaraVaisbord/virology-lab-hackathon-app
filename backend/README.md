# צד השרת – אימות טפסי התחייבות

FastAPI שמקבל קבצים, מפרק אותם לעמודים, מעבד כל עמוד ברקע ושומר את השדות לאימות של הלבורנטית.
סקירה כללית של המערכת: [`README.md`](../README.md) בתיקייה הראשית.

## התקנה והרצה

```bash
pip install -r requirements.txt     # pyzbar צריך גם את ספריית zbar (ראו למטה); לפיתוח: requirements-dev.txt
cp .env.example .env                # מפתחות Gemini; LLM_ENABLED=false כדי לעבוד בלי טוקנים
alembic upgrade head                # יצירה / עדכון של מסד הנתונים
python -m db.seed_senders           # טעינת רשימת השולחים המוכרים (אפשר להריץ שוב בלי נזק)
uvicorn main:app --port 8000
```

- **zbar:** Windows `winget install zbar` · macOS `brew install zbar` · Ubuntu `sudo apt-get install libzbar0`
- **Tesseract** (OCR מקומי): להתקין, ולשים בתיקייה `OCR_TESSDATA_DIR` את `heb`, `eng`, `osd` (‏tessdata_fast). בלי Tesseract המערכת עובדת, רק בלי שלב ה-OCR.
- **בדיקות:** `pytest`. על PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://… pytest`. בדיקת קוד: `ruff check .`, טיפוסים (מייעץ, לא חוסם): `mypy .`
- **עיבוד מחוץ לשרת:** `python -m scripts.extract_forms` (אימות מחדש של כל הטפסים), `--form 2 [--provider claude]`, `--local-only`.
- **בענן:** `Dockerfile` בתיקייה הזו (כולל Tesseract ו-zbar).

## איך עמוד מעובד

1. **העלאה** (`POST /uploads`) – הקובץ נשמר, כל עמוד הופך לתמונה **מיושרת** (סיבוב והטיה) ונוצרת שורה בטבלת `forms` בסטטוס `uploaded`.
2. **תור** – תהליכי רקע תופסים טפסים מהתור (`uploaded → processing`). התור שמור במסד הנתונים ושורד הפעלה מחדש.
3. **עיבוד מקדים** (`integrations/imaging/preprocessing.py`) – הסרת טוש צהוב, הפרדת דפוס / כתב יד / חותמות, ניקוי קווי טופס.
4. **שלושה מקורות נפרדים**, וכל אחד נשמר בנפרד (`barcode_result`, `ocr_result`, `llm_result`):
   - ברקודים – zbar
   - OCR מקומי – Tesseract; מוצא תוויות ("מספר התחייבות", "דרישה", "מרכזי", "התקבל"…) ואת הערך שלידן (`integrations/ocr/local_extractor.py`)
   - AI – Gemini ו-Claude לפי הסדר ב-`LLM_PROVIDERS`, אם `LLM_ENABLED=true` (`integrations/llm/`, ההנחיה ב-`prompts/`)
5. **הצלבה** (`domain/verification.py`) – ערך מסומן `verified` רק כשתווית שנקראה ב-OCR מוכיחה את השדה **וגם** שני מקורות קראו את אותו ערך. סתירה בין מקורות → `conflict`; מקור אחד → `unverified`; בעיית פורמט (ספרת ביקורת בת"ז, תאריך) → `uncertain`. כל מה שלא אומת עובר ללבורנטית.
6. טופס עובר ל-`approved` רק כשאין בו אף שדה שמחכה להחלטה.

**החלטות הלבורנטית נשמרות:** ערך שאישרה או תיקנה לא נדרס בעיבוד חוזר, וערך שמחקה לא חוזר (`forms.rejected_values`).
**היסטוריית תיקונים** (`field_events`): כל אישור, תיקון, החלפה, הוספה או מחיקה של ערך מוסיפים שורה. השורה נכתבת באותה טרנזקציה של הפעולה, ואף שורה לא נדרסת. נשמרים רק מהות השינוי (`change_kind`, למשל `typo`, ‏`wrong_field` או `day_month_swap`; מאיזה שדה הגיע הערך; אילו ספרות התחלפו, כמו `1>7`), איך הערך כתוב בעמוד (כתב יד, דפוס, מדבקה או ברקוד), ומצב השדה לפני השינוי. `previous_event_id` מחבר את ההיסטוריה של ערך גם אחרי החלפה או מחיקה של השורה שלו. **הערכים עצמם לא נשמרים** – הם נשארים ב-`extracted_fields`.
**קוד הכניסה** (`login_codes`): הקוד שממתין להקלדה נשמר במסד הנתונים (hash עם salt, תוקף ומונה ניסיונות), ולכן הוא עובד אחרי הפעלה מחדש ובכל replica. קודים שפג תוקפם נמחקים. כשיש יותר מ-replica אחד צריך להגדיר `AUTH_SECRET` (חתימת עוגיית ההתחברות).
**מכסת Gemini:** כשמפתח מגיע למכסה עוברים אוטומטית למפתח / מודל הבא; כשכולם במכסה, הטופס חוזר לתור והתור ממתין.

## איפה נמצא מה

| מה | איפה |
|---|---|
| כל ההגדרות (נתיבים, מגבלות, מודל Gemini, תור…) | `config.py` (`Settings`) – כל ערך אפשר לשנות דרך `.env` |
| בניית כל הרכיבים וחיבורם | `container.py` – המקום היחיד שיוצר רכיבים |
| שמות שדות, סטטוסים, תוויות בעברית, סיבות לספק | `domain/vocabulary.py` – מקור אמת יחיד, נשלח לממשק דרך `GET /meta` |
| כללי האימות וההצלבה / כללי הסקירה | `domain/verification.py`, `domain/review_rules.py` |
| שמירת קבצים ותמונות (תיקייה מקומית / S3) | `integrations/storage.py` |
| מסד הנתונים | `db/models.py`, `db/session.py`, גישה לנתונים ב-`db/repositories/`, מיגרציות ב-`alembic/` |
| עיבוד מקדים, OCR, ברקודים | `integrations/imaging/`, `integrations/ocr/` |
| ספקי ה-AI והמעבר ביניהם | `integrations/llm/` |
| צינור העיבוד ותור העיבוד | `services/extraction_pipeline.py`, `services/extraction_queue.py` |
| פעולות הלבורנטית (אישור, תיקון, מחיקה) | `services/review_service.py` |
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
| GET | `/forms/{id}` | טופס אחד, כולל מה שכל מקור קרא (`sources`), כל המספרים שנמצאו בעמוד ממוזגים בין המקורות (`page_numbers`) ומספרי התחייבות כפולים |
| GET | `/forms/{id}/image` | תמונת העמוד |
| PATCH | `/forms/{id}/fields/{field_id}/confirm` | אישור ערך (אפשר עם תיקון: `{"corrected_value": "..."}`) |
| POST | `/forms/{id}/fields` | הוספת ערך ידנית / בחירת מספר מהעמוד |
| DELETE | `/forms/{id}/fields/{field_id}` | מחיקת ערך (לא יחזור בעיבוד חוזר) |
| POST | `/forms/{id}/retry` | החזרת טופס שנכשל לתור |
| GET | `/insights/corrections` | דפוסים חוזרים בתיקונים של הלבורנטית, והמלצה לבדיקה לכל דפוס – `since`, `until`, `field_name`. בלי ערכים ובלי תמונות. זה **לא** מדד דיוק: שדות שאף אחד לא פתח לא נכללים (`coverage.auto_accepted_fields`). הספים ב-`INSIGHTS_*` |
| GET | `/health` | בדיקת תקינות |

כל הנתיבים מקבלים את הקידומת `API_PREFIX` (בענן: `/api/forms`…).
