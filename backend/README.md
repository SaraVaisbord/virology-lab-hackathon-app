# Barcode Reader – אב-טיפוס לקריאת ברקודים מטפסים רפואיים

עיבוד מקומי בלבד. אין שליחת תמונות לענן או ל-API חיצוני.

---

## דרישות מערכת

### 1. ספריית zbar (חובה ברמת מערכת ההפעלה)

`pyzbar` היא wrapper ל-`zbar`. **התקנת חבילת Python לבדה אינה מספיקה.**

**Windows:**
```
winget install zbar
```
או הורד את `zbar-x64.zip` מ-https://github.com/dani-garcia/zbar-wasm/releases  
ולחלופין השתמש ב-conda:
```
conda install -c conda-forge zbar
```

**macOS:**
```
brew install zbar
```

**Ubuntu / Debian:**
```
sudo apt-get install libzbar0
```

---

### 2. התקנת חבילות Python

```bash
pip install -r requirements.txt
```

---

## הרצה

```bash
python barcode_reader.py path/to/image.jpg
```

פורמטים נתמכים: `.png`, `.jpg`, `.jpeg`

---

## בדיקות

### בדיקה 1 – קובץ לא קיים
```bash
python barcode_reader.py no_such_file.jpg
```
פלט צפוי:
```
Error: File not found: no_such_file.jpg
```

### בדיקה 2 – תמונה ללא ברקוד
השג תמונה רגילה (למשל צילום נוף) והרץ:
```bash
python barcode_reader.py photo.jpg
```
פלט צפוי:
```
No barcodes found in image.
```

### בדיקה 3 – תמונה עם ברקוד
צור תמונת בדיקה עם ברקוד ידוע:
```python
# generate_test_barcode.py
from barcode import Code128
from barcode.writer import ImageWriter

with open("test_barcode.png", "wb") as f:
    Code128("MED-2024-001234", writer=ImageWriter()).write(f)
```
התקן: `pip install python-barcode`  
הרץ: `python generate_test_barcode.py`  
לאחר מכן:
```bash
python barcode_reader.py test_barcode.png
```
פלט צפוי:
```
Found 1 barcode(s).
  [1] type=CODE128  data=MED-2024-001234  pos=(...)  size=...x...
```

> **שים לב:** תוצאות הבדיקות לעיל לא הורצו אוטומטית. יש להריץ אותן ידנית לאחר התקנת `zbar`.

---

## אבטחה

- כל העיבוד מתבצע מקומית.
- אין שמירת תמונות או תוצאות מעבר לפלט הטרמינל.
- אין לוגים שמדפיסים מידע רפואי כברירת מחדל.
