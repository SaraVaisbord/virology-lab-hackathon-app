import {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, ShadingType
} from 'docx'
import { writeFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(__dirname, '../../Design System')
const OUTPUT = resolve(OUT_DIR, 'UI_Design_System_and_Screens.docx')

mkdirSync(OUT_DIR, { recursive: true })

// ─── Helpers ────────────────────────────────────────────────────────────────
const h1 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 400, after: 200 } })
const h2 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 150 } })
const p  = (text) => new Paragraph({ children: [new TextRun({ text, size: 22, font: 'Arial' })], spacing: { after: 120 }, bidirectional: true })
const bullet = (text) => new Paragraph({ children: [new TextRun({ text, size: 22, font: 'Arial' })], bullet: { level: 0 }, spacing: { after: 80 }, bidirectional: true })
const bold = (text) => new Paragraph({ children: [new TextRun({ text, bold: true, size: 22, font: 'Arial' })], spacing: { after: 80 }, bidirectional: true })
const code = (text) => new Paragraph({ children: [new TextRun({ text, font: 'Courier New', size: 18 })], spacing: { after: 120 } })
const divider = () => new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' } }, spacing: { before: 200, after: 200 } })

const th = (cells) => new TableRow({
  tableHeader: true,
  children: cells.map(c => new TableCell({
    shading: { type: ShadingType.SOLID, color: '1e3a6e' },
    children: [new Paragraph({ children: [new TextRun({ text: c, bold: true, color: 'FFFFFF', size: 20, font: 'Arial' })] })]
  }))
})

const tr = (...cells) => new TableRow({
  children: cells.map(c => new TableCell({
    children: [new Paragraph({ children: [new TextRun({ text: c, size: 20, font: 'Arial' })] })]
  }))
})

// ─── Document ───────────────────────────────────────────────────────────────
const doc = new Document({
  creator: 'Sara Vaisbord',
  title: 'UI Design System – מערכת אימות טפסים',
  sections: [{
    properties: { page: { margin: { top: 1000, bottom: 1000, left: 1200, right: 1200 } } },
    children: [

      // Cover
      new Paragraph({ children: [new TextRun({ text: 'מערכת אימות טפסים רפואיים', bold: true, size: 52, font: 'Arial', color: '1e3a6e' })], alignment: AlignmentType.CENTER, spacing: { before: 600, after: 200 } }),
      new Paragraph({ children: [new TextRun({ text: 'המעבדה המרכזית לנגיפים', size: 32, font: 'Arial', color: '14b8a6' })], alignment: AlignmentType.CENTER, spacing: { after: 100 } }),
      new Paragraph({ children: [new TextRun({ text: 'UI Design System & Screen Map', size: 26, font: 'Arial', color: '666666' })], alignment: AlignmentType.CENTER, spacing: { after: 100 } }),
      new Paragraph({ children: [new TextRun({ text: 'האקתון קוד פתוח – בשיתוף משרד הבריאות 2026', size: 22, font: 'Arial', color: '999999' })], alignment: AlignmentType.CENTER, spacing: { after: 100 } }),
      new Paragraph({ children: [new TextRun({ text: 'כל הזכויות שמורות לSara Vaisbord', size: 20, font: 'Arial', color: 'AAAAAA' })], alignment: AlignmentType.CENTER, spacing: { after: 500 } }),
      divider(),

      // 1. Overview
      h1('1. סקירה כללית'),
      p('מערכת MVP פנימית לאימות נתונים מטפסים רפואיים (טפסי התחייבות) עבור לבורנטיות המעבדה המרכזית לנגיפים.'),
      p('המערכת מחלצת נתונים באמצעות OCR ו-LLM (Gemini), משווה תוצאות, ומאפשרת אימות ותיקון ידני של שדות לא ודאיים.'),
      p('Stack: React 18 + Vite + Tailwind CSS 3 + Lucide Icons + פונט Heebo'),
      divider(),

      // 2. Screen Map
      h1('2. מיפוי מסכים'),

      h2('2.1 מסך ראשי – לוח בקרה (Dashboard)'),
      p('קובץ: App.jsx | נתיב: /'),
      bullet('Header – סרגל ניווט עליון דביק (sticky, h-20)'),
      bullet('כותרת עמוד – "לוח בקרה – אימות טפסים"'),
      bullet('StatsCards – 3 כרטיסיות סיכום אינטראקטיביות'),
      bullet('DataTable – טבלת נתונים עם גלילה פנימית (max-h-60vh) וכותרות דביקות'),
      bullet('Legend – מקרא צבעים'),
      bullet('Footer – פוטר קבוע'),

      h2('2.2 חלונית אימות שדה (Validation Modal)'),
      p('נפתחת מעל המסך הראשי בלחיצה על שדה "לא בטוח" בטבלה.'),
      bullet('תצוגת אזור תמונה מקורי (placeholder לחיבור API עתידי)'),
      bullet('הצגת ערך שחולץ וסיבת הספק (רקע ורוד bg-pink-50)'),
      bullet('שדה קלט לתיקון ידני עם focus ring teal'),
      bullet('כפתורי "אישור שדה" (teal) ו-"שמירה וסגירה" (navy)'),
      bullet('נסגרת ב-Escape, לחיצה על רקע, או כפתור X'),

      divider(),

      // 3. Components
      h1('3. רכיבים (Components)'),

      h2('3.1 Header – src/components/Header.jsx'),
      bullet('גובה: h-20 (80px) | רקע: rgba(255,255,255,0.95) + backdrop-blur(12px)'),
      bullet('לוגו המעבדה (h-12) → קישור # | לוגו משרד הבריאות (h-10) → gov.il | לוגו שיבא (h-9) → sheba.co.il'),
      bullet('קווי הפרדה אנכיים בין הלוגואים (w-px h-10 bg-gray-200)'),
      bullet('כפתור dark mode (w-11 h-11) | אווטאר משתמש (w-10 h-10) + שם + ChevronDown'),

      h2('3.2 StatsCards – src/components/StatsCards.jsx'),
      bullet('כרטיסייה 1 "ממתינים": sky-500 | לחיצה → סינון pending'),
      bullet('כרטיסייה 2 "דיוק": teal-500 | לא לחיצה'),
      bullet('כרטיסייה 3 "לאימות": amber-500 | לחיצה → סינון uncertain/not_found'),
      bullet('אנימציית Count-up (1200ms ease-out cubic) בטעינה'),
      bullet('Layout: טקסט ימין, אייקון שמאל, items-center justify-between'),
      bullet('מצב פעיל: ring-2 + רקע פסטלי + תגית "מסנן פעיל"'),

      h2('3.3 DataTable – src/components/DataTable.jsx'),
      bullet('מעטפת: max-h-[60vh] + overflow-y-auto + custom scrollbar (w-1.5, rounded)'),
      bullet('כותרות: sticky top-0 z-10 + backdrop-blur-sm + gradient אפור-תכלת'),
      bullet('שדה uncertain: bg-pink-50, border-pink-200, text-pink-600, rounded-full'),
      bullet('Badge "אושר": teal pill | Badge "ממתין": amber pill'),
      bullet('Hover שורה: bg-slate-50'),

      h2('3.4 ValidationModal – src/components/ValidationModal.jsx'),
      bullet('אנימציה: animate-fade-in + animate-slide-up (250ms)'),
      bullet('סיבת ספק: bg-pink-50 + text-pink-600 + border-pink-200'),
      bullet('שמירה: מעדכנת status ל-confirmed, מחשבת מחדש status הטופס'),


      h2('3.6 Footer – src/components/Footer.jsx'),
      bullet('רקע: #F0F4F3 | padding: py-6'),
      bullet('ימין: "אודות המערכת" + טקסט + קו + לוגו קוד פתוח + קרדיט האקתון'),
      bullet('שמאל: קישורים + "כל הזכויות שמורות לSara Vaisbord © 2026"'),
      divider(),

      // 4. Colors
      h1('4. פלטת צבעים'),
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          th(['שם', 'Tailwind', 'HEX', 'שימוש']),
          tr('Navy 600', 'navy-600', '#1e3a6e', 'כותרות, אייקונים, כפתור שמירה'),
          tr('Navy 700', 'navy-700', '#162d57', 'טקסט ראשי'),
          tr('Navy 800', 'navy-800', '#0f2040', 'כותרות עמוד, מספרים'),
          tr('Sky 500', 'sky-500', '#0ea5e9', 'כרטיסיית ממתינים, hover עיפרון'),
          tr('Teal 500', 'teal-500', '#14b8a6', 'כרטיסיית דיוק, כפתורים, badge אושר'),
          tr('Amber 500', 'amber-500', '#f59e0b', 'כרטיסיית לאימות, badge ממתין'),
          tr('Pink 50', 'pink-50', '#fdf2f8', 'רקע שדות uncertain וסיבת ספק'),
          tr('Pink 600', 'pink-600', '#db2777', 'טקסט שדות uncertain'),
          tr('Pink 200', 'pink-200', '#fbcfe8', 'מסגרת שדות uncertain'),
          tr('רקע עמוד', '—', '#F4F7F6', 'רקע כללי'),
          tr('רקע פוטר', '—', '#F0F4F3', 'רקע פוטר'),
          tr('White', 'white', '#FFFFFF', 'כרטיסיות, טבלה'),
          tr('Gray 950', 'gray-950', '#030712', 'רקע dark mode'),
        ]
      }),
      divider(),

      // 5. Typography
      h1('5. טיפוגרפיה'),
      bold('פונט: Heebo (Google Fonts) | גיבוי: Assistant, sans-serif | כיוון: RTL'),
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          th(['אלמנט', 'גודל', 'משקל', 'צבע']),
          tr('כותרת עמוד', 'text-xl / 20px', 'font-bold 700', 'navy-800'),
          tr('מספרים בכרטיסיות', 'text-4xl / 36px', 'font-black 900', 'navy-800'),
          tr('כותרת Header', 'text-base / 16px', 'font-bold 700', 'navy-800'),
          tr('תאים בטבלה', 'text-sm / 14px', 'font-medium 500', 'gray-700'),
          tr('כותרות עמודות', 'text-xs / 12px', 'font-bold 700', 'navy-700'),
          tr('טקסט משני', 'text-xs / 12px', 'font-normal 400', 'gray-400'),
        ]
      }),
      divider(),

      // 6. Interactions
      h1('6. אינטראקציות ומצבים'),

      h2('6.1 סינון טבלה'),
      bullet('לחיצה על כרטיסייה 1: מסננת status=pending'),
      bullet('לחיצה על כרטיסייה 3: מסננת שדות uncertain/not_found'),
      bullet('לחיצה חוזרת: מבטלת סינון (toggle)'),
      bullet('Badge ביטול בכותרת הטבלה עם כפתור ✕'),

      h2('6.2 שדות לא ודאיים'),
      bullet('Hover: border-pink-400 + bg-pink-50/80'),
      bullet('לחיצה: פותחת ValidationModal'),
      bullet('לאחר שמירה: status → confirmed, אם כל השדות confirmed → טופס → approved'),

      h2('6.3 לוגואים בהדר'),
      bullet('משרד הבריאות → https://www.gov.il/he/departments/ministry_of_health'),
      bullet('שיבא → https://www.sheba.co.il'),
      bullet('המעבדה → # (placeholder)'),
      bullet('Hover: opacity 70% → 100%'),

      h2('6.4 Dark Mode'),
      bullet('מנגנון: document.documentElement.classList.toggle("dark")'),
      bullet('הפעלה: כפתור בהדר'),
      divider(),

      // 7. Data
      h1('7. מבנה נתונים'),
      p('קובץ: src/data/mockData.js'),
      bold('Form Object:'),
      code('{ id, fileName, uploadDate, pages, totalBarcodes, status: "pending"|"approved", fields: {...} }'),
      bold('Field Object:'),
      code('{ value, status: "confirmed"|"uncertain"|"not_found", reason?, page?, x?, y?, width?, height? }'),
      divider(),

      // 8. File Structure
      h1('8. מבנה קבצים'),
      code('fronend/'),
      code('├── public/logos/   moh.png | sheba.svg | virus-lab.png | open-code.png'),
      code('├── src/components/ Header | StatsCards | DataTable | ValidationModal | Footer'),
      code('├── src/data/       mockData.js'),
      code('├── src/            App.jsx | main.jsx | index.css'),
      code('└──                 tailwind.config.js | vite.config.js | package.json'),
      divider(),

      new Paragraph({
        children: [new TextRun({ text: 'כל הזכויות שמורות לSara Vaisbord © 2026', size: 18, font: 'Arial', color: 'AAAAAA' })],
        alignment: AlignmentType.CENTER,
        spacing: { before: 400 },
      }),
    ]
  }]
})

Packer.toBuffer(doc).then(buffer => {
  writeFileSync(OUTPUT, buffer)
  console.log('SUCCESS:', OUTPUT)
})
