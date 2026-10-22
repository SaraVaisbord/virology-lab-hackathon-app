// Generates "Design System/UI_Design_System_and_Screens.docx": the system's architecture, processing flow, screens
// and design tokens, as they are in the code. Run from frontend/: node scripts/generate-docs.mjs
import {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, ShadingType, LevelFormat,
} from 'docx'
import { writeFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(__dirname, '../../Design System')
const OUTPUT = resolve(OUT_DIR, 'UI_Design_System_and_Screens.docx')
mkdirSync(OUT_DIR, { recursive: true })

// ─── Style ──────────────────────────────────────────────────────────────────
const FONT = 'Arial'
const NAVY = '1E3A6E'
const TEAL = '0F9D94'
const PAGE_WIDTH = 11906 // A4, DXA
const MARGIN = 1134 // 2 cm
const CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

// ─── Helpers (right-to-left Hebrew text; code and identifiers stay left-to-right) ──
const run = (text, options = {}) => new TextRun({ text, font: FONT, size: 22, rightToLeft: true, ...options })
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, bidirectional: true, spacing: { before: 360, after: 160 }, children: [run(text, { size: 32, bold: true, color: NAVY })] })
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, bidirectional: true, spacing: { before: 240, after: 120 }, children: [run(text, { size: 26, bold: true, color: TEAL })] })
const p = (text) => new Paragraph({ bidirectional: true, spacing: { after: 120 }, children: [run(text)] })
const bullet = (text) => new Paragraph({ bidirectional: true, numbering: { reference: 'bullets', level: 0 }, spacing: { after: 60 }, children: [run(text)] })
const step = (text) => new Paragraph({ bidirectional: true, numbering: { reference: 'steps', level: 0 }, spacing: { after: 60 }, children: [run(text)] })
const code = (text) => new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text, font: 'Consolas', size: 18 })] })
const divider = () => new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'CCCCCC', space: 1 } }, spacing: { before: 160, after: 160 } })

const cellBorder = { style: BorderStyle.SINGLE, size: 4, color: 'D0D7E2' }
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder }

/** A table with a navy header row; widths are fractions of the content width. */
function table(headers, rows, fractions) {
  const widths = fractions.map((fraction) => Math.round(fraction * CONTENT_WIDTH))
  widths[widths.length - 1] += CONTENT_WIDTH - widths.reduce((sum, width) => sum + width, 0)
  const cell = (text, index, header) => new TableCell({
    width: { size: widths[index], type: WidthType.DXA },
    borders,
    shading: header ? { type: ShadingType.CLEAR, fill: NAVY, color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ bidirectional: true, children: [run(text, { size: 19, bold: header, color: header ? 'FFFFFF' : undefined })] })],
  })
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: widths,
    visuallyRightToLeft: true,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((text, index) => cell(text, index, true)) }),
      ...rows.map((row) => new TableRow({ children: row.map((text, index) => cell(text, index, false)) })),
    ],
  })
}

// ─── Content ────────────────────────────────────────────────────────────────
const cover = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1200, after: 200 }, children: [run('מערכת אימות טפסי התחייבות', { size: 52, bold: true, color: NAVY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run('המעבדה המרכזית לנגיפים – המרכז הרפואי שיבא', { size: 30, color: TEAL })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run('ארכיטקטורת המערכת, זרימת העיבוד, מסכים ומערכת העיצוב', { size: 26, color: '555555' })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [run('האקתון קוד פתוח – בשיתוף משרד הבריאות 2026', { size: 22, color: '888888' })] }),
  divider(),
]

const overview = [
  h1('1. סקירה כללית'),
  p('המערכת קולטת טפסי התחייבות סרוקים, מחלצת מהם את הפרטים שהמעבדה צריכה, מצליבה כל ערך מול מקורות בלתי תלויים, ומציגה ללבורנטית רק את מה שדורש החלטה. נתונים מאושרים מיוצאים לאקסל – שורה לכל מספר התחייבות.'),
  p('השדות שמחולצים: שם פרטי, שם משפחה, תעודת זהות, מספר התחייבות (מפתח השורה בייצוא), מספר מרכזי (יכולים להיות כמה), תאריך קבלה וגורם שולח. מספרים לא רלוונטיים – טלפון, פקס, כתובת, מיקוד, מחלקה ורישיון רופא – מסוננים בכל שלב.'),
]

const architecture = [
  h1('2. ארכיטקטורה'),
  p('שלושה רכיבים: ממשק דפדפן, שרת אחד שמכיל גם את תור העיבוד, ושכבת נתונים. מודלי השפה הם שירות חיצוני; זיהוי הברקודים והטקסט רצים על השרת עצמו.'),
  code('דפדפן (React)  ──/api──►  שרת FastAPI ──► מסד נתונים (SQLite מקומית / PostgreSQL בענן)'),
  code('                           │          ──► קבצים ותמונות (תיקייה מקומית / S3 פרטי)'),
  code('                           ├─ תור עיבוד ── ניקוי תמונה · ברקודים · OCR  (מקומי)'),
  code('                           └─ מודל שפה ── Claude ─► Gemini גיבוי   (API חיצוני)'),
  new Paragraph({ spacing: { after: 160 } }),
  table(['רכיב', 'טכנולוגיה', 'תפקיד'], [
    ['ממשק', 'React 18, Vite, Tailwind CSS', 'מסך כניסה, טבלת טפסים, מסך אימות, מסך תובנות. פונה לשרת דרך הכתובת שלו (/api), בלי CORS'],
    ['שרת', 'Python, FastAPI', 'נקודות הקצה, אכיפת התחברות, תור העיבוד, ההצלבה והייצוא'],
    ['תור עיבוד', 'תהליכון ברקע בתוך השרת', 'לוקח עמודים שהועלו ומעבד אותם; כשכל ספקי ה-AI לא זמינים – מחזיר לתור וממתין'],
    ['ניקוי תמונה', 'OpenCV', 'יישור סיבוב והטיה, איזון תאורה, הסרת מרקר צהוב, הפרדת שכבות דפוס / עט / חותמות'],
    ['ברקודים', 'zbar', 'קריאת ברקודים בכמה גרסאות של התמונה'],
    ['זיהוי טקסט', 'Tesseract OCR', 'מציאת תוויות ("מספר התחייבות", "מרכזי", "התקבל") והערך שלידן'],
    ['מודל שפה', 'Claude (Anthropic), Gemini (Google)', 'קורא את תמונת העמוד ומחזיר את השדות במבנה JSON קבוע'],
    ['מסד נתונים', 'SQLAlchemy + Alembic; SQLite / PostgreSQL', 'טפסים, ערכים, היסטוריית תיקונים, רשימת שולחים. המיגרציות רצות על שני סוגי המסד'],
    ['אחסון קבצים', 'תיקייה מקומית / Amazon S3', 'הקבצים שהועלו ותמונות העמודים – לעולם לא בתוך מסד הנתונים'],
  ], [0.17, 0.3, 0.53]),
]

const flow = [
  h1('3. זרימת המערכת'),
  step('התחברות: הלבורנטית מזינה מייל ומקבלת קוד חד-פעמי. בלי סשן תקף השרת חוסם כל בקשה, כולל תמונות ונתונים.'),
  step('העלאה: PDF או תמונות. כל עמוד הופך לתמונה מיושרת, נשמר, ונכנס לתור בסטטוס "בתור לעיבוד".'),
  step('ניקוי התמונה: גרסה נקייה של העמוד מחליפה את המקורית – כל המקורות והממשק עובדים על אותה גאומטריה.'),
  step('קריאה משלושה מקורות בלתי תלויים: ברקודים, OCR מקומי, ומודל שפה. התוצאה הגולמית של כל מקור נשמרת בנפרד, כך שכשל של מקור אחד לא מוחק את האחרים.'),
  step('הצלבה: ערך מסומן "אומת משני מקורות" רק כשתווית שזוהתה מוכיחה את השדה וגם שני מקורות קראו את אותו ערך. סתירה – "סתירה בין מקורות"; מקור אחד – "לא מאומת"; בעיית פורמט (ספרת ביקורת בת"ז, תאריך) – "לא ודאי".'),
  step('אימות: הלבורנטית רואה את הטופס עם הערך מסומן עליו, את מה שכל מקור קרא ואת כל המספרים בעמוד – ומאשרת, מתקנת, בוחרת מספר מהעמוד, מוסיפה או מוחקת. החלטה אנושית לא נדרסת בעיבוד חוזר, וערך שנמחק לא חוזר.'),
  step('תיעוד: כל פעולה נרשמת בהיסטוריית התיקונים, באותה טרנזקציה, בלי לשמור את הערכים עצמם.'),
  step('אישור וייצוא: טופס עובר ל"אושר" כשאין בו שדה שממתין להחלטה. הייצוא לאקסל יוצר שורה לכל מספר התחייבות.'),
]

const ai = [
  h1('4. מודלי השפה – איפה המודל ואיך עוברים בין ספקים'),
  p('המודלים נקראים דרך ה-API של הספקים. לכל ספק מודול עם אותו ממשק בדיוק (extract_from_image), אותה הנחיה (prompts/extraction_prompt.md) ואותו מבנה תשובה – לכן כל השלבים שאחרי המודל לא תלויים בספק.'),
  bullet('סדר הספקים מוגדר ב-LLM_PROVIDERS: ברירת המחדל Claude ואחריו Gemini. הספק הראשון שעונה – קורא את העמוד, והתשובה שומרת מי ענה.'),
  bullet('לכל ספק כמה מפתחות. מפתח שהגיע למכסה או נדחה נח לזמן מה והבא בתור ממשיך.'),
  bullet('מודל עמוס נח על כל המפתחות יחד – העומס הוא של הספק ולא של המפתח, ולכן עמוד לא נשלח אליו שוב עם מפתח אחר.'),
  bullet('כשכל הספקים נחים – העמוד חוזר לתור והתור ממתין. כשספק נכשל על העמוד עצמו – הטופס מסומן כנכשל, כדי לא לשרוף טוקנים בלולאה.'),
  bullet('Claude: מודל claude-opus-5-5 (ניתן לשינוי), תשובה במבנה JSON קבוע, וניתוב שרת אוטומטי למודל Claude אחר אם הבקשה נדחית.'),
  bullet('למודל נשלחת התמונה הנקייה של העמוד (מוקטנת ל-1600 פיקסלים, JPEG) – לא תוצאות ה-OCR, כדי שיישאר מקור בלתי תלוי.'),
]

const statuses = [
  h1('5. סטטוסים'),
  table(['סטטוס שדה', 'משמעות', 'דורש החלטה'], [
    ['אומת משני מקורות', 'תווית מוכיחה את השדה ושני מקורות קראו את אותו ערך', 'לא'],
    ['סתירה בין מקורות', 'המקורות קראו ערכים שונים', 'כן'],
    ['לא מאומת', 'הערך נקרא במקור אחד בלבד', 'כן'],
    ['לא ודאי', 'בעיית פורמט או ביטחון נמוך', 'כן'],
    ['לא נמצא', 'השדה לא נמצא בעמוד', 'כן'],
    ['אושר', 'הלבורנטית החליטה (אישרה, תיקנה או הוסיפה)', 'לא'],
  ], [0.25, 0.6, 0.15]),
  new Paragraph({ spacing: { after: 120 } }),
  p('סטטוס טופס: בתור לעיבוד ← בעיבוד ← ממתין לאימות ← אושר; או נכשל (אפשר להחזיר לתור).'),
]

const data = [
  h1('6. מודל הנתונים'),
  table(['טבלה', 'מה נשמר'], [
    ['forms', 'עמוד אחד של קובץ שהועלה: שם הקובץ, טביעת התוכן (לזיהוי כפילויות), מיקום תמונת העמוד באחסון, סוג הטופס, סטטוס, התוצאה הגולמית של כל מקור בנפרד, וערכים שהלבורנטית מחקה'],
    ['extracted_fields', 'ערך אחד של שדה: הערך המוצג, מה שכל מקור קרא, התיקון, סטטוס, רמת ביטחון, הסיבה לספק, הראיות (JSON) ומיקום על העמוד. לשדות מרובי ערכים – שורה לכל ערך'],
    ['field_events', 'היסטוריית התיקונים: שורה לכל פעולה של הלבורנטית – סוג הפעולה, מהות השינוי (למשל טעות בספרה, ערך ששייך לשדה אחר, היפוך יום וחודש), מצב השדה לפני השינוי, וקישור לאירוע הקודם. בלי הערכים עצמם'],
    ['senders', 'רשימת הגורמים השולחים המוכרים'],
  ], [0.22, 0.78]),
  new Paragraph({ spacing: { after: 120 } }),
  p('מקור אמת יחיד לשמות השדות, הסטטוסים והתוויות בעברית: backend/db/constants.py. הממשק מקבל אותם מ-GET /meta ולא מחזיק עותק משלו.'),
]

const auth = [
  h1('7. התחברות ואבטחה'),
  bullet('כניסה בקוד חד-פעמי בן 6 ספרות שנשלח במייל (SMTP). הקוד תקף 10 דקות, לשימוש אחד; אחרי 5 טעויות הוא נפסל; קוד חדש לכל היותר פעם בדקה.'),
  bullet('אחרי הכניסה: עוגיית סשן חתומה, לא נגישה לקוד בדף, תקפה 12 שעות. שכבת ביניים בשרת חוסמת כל בקשה בלי סשן, חוץ מבדיקת התקינות ושלבי הכניסה.'),
  bullet('מצב הדגמה: AUTH_DEMO_CODE מאפשר כניסה בקוד קבוע בלי שליחת מייל – לדמו בלבד, להסיר לפני נתונים אמיתיים.'),
  bullet('מפתחות API וסיסמאות: בקובץ .env מקומית ובכספת AWS Secrets Manager בענן – לעולם לא ב-Git. קודים, מפתחות וערכי מטופלים לא נכתבים ליומנים.'),
  bullet('לפני נתונים אמיתיים: HTTPS בלבד ו-AUTH_COOKIE_SECURE=true, והסכמה לעיבוד תמונות העמודים אצל ספקי ה-AI.'),
]

const insights = [
  h1('8. היסטוריית תיקונים ותובנות'),
  p('כל תיקון של הלבורנטית מסווג אוטומטית ונשמר בלי מידע מזהה. מנקודת הקצה GET /insights/corrections ומסך "תובנות מתיקונים" אפשר לראות דפוסים חוזרים: שדה שמתוקן לעתים קרובות, ערך שסומן כמאומת ובכל זאת תוקן, בלבול חוזר בין שתי ספרות, ערך ששויך לשדה הלא נכון, היפוך יום וחודש, ערכים שה-AI החמיץ או הוסיף, ומקור אחר שקרא נכון.'),
  p('לכל תובנה: מספר האירועים, התקופה, רמת ביסוס והמלצה לבדיקה. תובנה עם מעט אירועים מוצגת כ"חשד ראשוני". כשאין מספיק נתונים מוצגת הודעה – לא ממציאים תובנות. המספרים אינם מדד דיוק: שדות שאושרו אוטומטית ולא נפתחו לא נכללים בחישוב, והמסך אומר זאת.'),
]

const api = [
  h1('9. נקודות הקצה (API)'),
  table(['נתיב', 'תיאור'], [
    ['GET /auth/status · POST /auth/request-code · /auth/verify · /auth/logout', 'התחברות בקוד חד-פעמי'],
    ['POST /uploads', 'העלאת קבצים'],
    ['GET /forms · /forms/{id} · /forms/{id}/image · /forms/summary', 'רשימה עם דפדוף, סינון ומיון; טופס אחד; תמונת העמוד; סיכום ומצב התור'],
    ['PATCH /forms/{id}/fields/{field_id}/confirm', 'אישור ערך, אפשר עם תיקון'],
    ['POST /forms/{id}/fields · DELETE /forms/{id}/fields/{field_id}', 'הוספת ערך (הקלדה או בחירה מהעמוד) ומחיקה'],
    ['POST /forms/{id}/retry · DELETE /forms/{id}', 'החזרה לתור; מחיקת רשומה'],
    ['GET /forms/export', 'ייצוא לאקסל'],
    ['GET /insights/corrections', 'דפוסי טעויות חוזרים'],
    ['GET /meta', 'אוצר המילים והתוויות לממשק'],
  ], [0.55, 0.45]),
]

const screens = [
  h1('10. מסכי הממשק'),
  h2('10.1 מסך כניסה – auth/AuthGate.jsx'),
  bullet('מוצג לפני כל השאר. שלב 1: כתובת מייל ו"שלחו לי קוד". שלב 2: קוד בן 6 ספרות ו"כניסה", או "שלחו קוד חדש".'),
  h2('10.2 טבלת הטפסים – App.jsx'),
  bullet('Header: לוגואים, ניווט בין "טפסים" ל"תובנות מתיקונים", מצב כהה, יציאה.'),
  bullet('ProcessingBanner: התקדמות התור, טפסים שנכשלו, והשהיה כשכל ספקי ה-AI לא זמינים.'),
  bullet('TableToolbar: סינון לפי סטטוס, חיפוש חופשי, העלאת קבצים (UploadPanel) וייצוא לאקסל.'),
  bullet('DataTable: שורה לכל עמוד, עם סינון לכל עמודה, מיון וטעינה בהמשכים. ערך שדורש החלטה מודגש בצבע "לבדיקה".'),
  h2('10.3 מסך אימות – form-details/FormDetailsModal.jsx'),
  bullet('DocumentViewer: תמונת העמוד עם הערך הנבחר מסומן עליה, וגלילה אליו.'),
  bullet('FieldList ו-FieldEditor: כל השדות; אישור, תיקון, הוספה ומחיקה. PageNumberRow: כל מספר שנמצא בעמוד – אפשר להציג ולשייך לשדה.'),
  bullet('PageSources: מה כל מקור קרא. DuplicateCompare: השוואת שני העמודים כשמספר התחייבות מופיע בשני טפסים.'),
  h2('10.4 תובנות מתיקונים – insights/CorrectionInsightsDashboard.jsx'),
  bullet('בחירת תקופה ושדה, כרטיסי סיכום, תרשים "אילו שדות מתוקנים הכי הרבה?" עם תצוגת טבלה, וכרטיס לכל תובנה (InsightCard).'),
  bullet('תובנה מבוססת – מסגרת רציפה בצבע teal; חשד ראשוני – מסגרת מקווקוות בצבע "לבדיקה". מצבי טעינה, שגיאה ו"אין עדיין מספיק נתונים".'),
]

const designSystem = [
  h1('11. מערכת העיצוב'),
  p('Tailwind CSS עם צבעים מוגדרים ב-tailwind.config.js, ומחלקות משותפות ב-index.css. סגנונות של וריאנטים (כרטיסי תובנה, תגיות סטטוס) מרוכזים ב-theme.js וב-StatusBadge – לא מוגדרים בכל רכיב מחדש. אייקונים: lucide-react. כיוון: RTL.'),
  table(['טוקן', 'ערך', 'שימוש'], [
    ['navy-600 / 800', '#1e3a6e / #0f2040', 'כותרות, טקסט ראשי'],
    ['teal-500 / 600', '#0f9d94 / #0d7c76', 'פעולה ראשית, "אושר", תובנה מבוססת, תרשים'],
    ['review-50 … 950', '#fffbeb … #451a03 (ענבר)', 'כל מה שדורש החלטה של הלבורנטית – מקום אחד לשינוי הצבע'],
    ['orange (ring)', 'orange-200 / 500', 'סתירה בין מקורות – חמור מ"לבדיקה"'],
    ['surface-page / card', '#F4F7F6 / #FFFFFF', 'רקע העמוד וכרטיסים'],
    ['מצב כהה', 'slate-900 / 950', 'רקע במצב כהה (class="dark")'],
  ], [0.25, 0.3, 0.45]),
  new Paragraph({ spacing: { after: 120 } }),
  bullet('טיפוגרפיה: Heebo (גיבוי Assistant); כותרת עמוד text-xl מודגש, טבלה text-sm, טקסט משני text-xs.'),
  bullet('רכיבי בסיס: .card (רקע לבן, צל עדין, פינות מעוגלות), .btn-primary (teal), .btn-ghost, ModalShell לחלונות.'),
]

const cloud = [
  h1('12. פריסה בענן'),
  p('שתי תמונות Docker (שרת, ממשק) רצות על Amazon EKS מאחורי Application Load Balancer: /api לשרת, השאר לממשק. מסד הנתונים הוא Amazon RDS PostgreSQL בתת-רשת פרטית עם גיבויים; הקבצים בבאקט S3 פרטי, מוצפן ועם גרסאות; הסודות ב-Secrets Manager ומגיעים לשרת דרך External Secrets; לשרת הרשאה רק לבאקט שלו (IRSA). התשתית מוגדרת ב-Terraform (virology-lab-hackathon-infra) והפריסה בקובצי Kubernetes וסקריפט (virology-lab-hackathon-k8s).'),
]

const structure = [
  h1('13. מבנה הקוד'),
  code('backend/'),
  code('  api/            auth · uploads · forms · insights · meta'),
  code('  services/       extraction_queue · extraction_service · llm_router · insights_service · auth_service · export_service'),
  code('  db/             models · queries · constants (מקור אמת יחיד)'),
  code('  claude_extractor.py · ai_extractor.py (Gemini) · local_extractor.py (OCR) · preprocessing.py'),
  code('  prompts/  alembic/  tests/'),
  code('frontend/src/'),
  code('  auth/  components/ (form-details, insights, ui)  hooks/  lib/  meta/  theme.js'),
  new Paragraph({ spacing: { after: 160 } }),
  h1('14. כלים'),
  p('המערכת תוכננה, נכתבה, נבדקה ונפרסה בעזרת Claude Code.'),
]

// ─── Document ───────────────────────────────────────────────────────────────
const doc = new Document({
  creator: 'Sara Vaisbord',
  title: 'מערכת אימות טפסי התחייבות – ארכיטקטורה ומערכת עיצוב',
  styles: { default: { document: { run: { font: FONT, size: 22 } } } },
  numbering: {
    config: [
      { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.RIGHT, style: { paragraph: { indent: { right: 500, hanging: 280 } } } }] },
      { reference: 'steps', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.RIGHT, style: { paragraph: { indent: { right: 500, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: PAGE_WIDTH, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    children: [
      ...cover, ...overview, ...architecture, ...flow, ...ai, ...statuses, ...data, ...auth, ...insights, ...api,
      ...screens, ...designSystem, ...cloud, ...structure,
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400 }, children: [run('כל הזכויות שמורות ל-Sara Vaisbord © 2026', { size: 18, color: 'AAAAAA' })] }),
    ],
  }],
})

Packer.toBuffer(doc).then((buffer) => {
  writeFileSync(OUTPUT, buffer)
  console.log('SUCCESS:', OUTPUT)
})
