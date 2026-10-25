import { useEffect, useRef, useState } from 'react'
import { ImageOff, X, ZoomIn, ZoomOut } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

const ZOOM_MIN = 1
const ZOOM_MAX = 3
const ZOOM_STEP = 0.5
const HIGHLIGHT_PADDING = 0.006 // a little breathing room around the value (normalized units)
const DIM_PAGE = 'shadow-[0_0_0_9999px_rgba(15,23,42,0.28)]'

const hasBox = (field) => [field?.x, field?.y, field?.width, field?.height].every((value) => typeof value === 'number')
const pct = (value) => `${(value * 100).toFixed(2)}%`
const boxStyle = (box) => ({
  left: pct(Math.max(0, box.x - HIGHLIGHT_PADDING)),
  top: pct(Math.max(0, box.y - HIGHLIGHT_PADDING)),
  width: pct(box.width + HIGHLIGHT_PADDING * 2),
  height: pct(box.height + HIGHLIGHT_PADDING * 2),
})

/**
 * Page image with the active field highlighted (review colour) and, when the lab worker clicks "show" on a number
 * found on the page, that number highlighted too (teal, with its value) — the page is dimmed around whichever
 * one is in focus. Coordinates are normalized (0..1) to the image.
 */
export default function DocumentViewer({ imageUrl, field, focus, onClearFocus, alt }) {
  const meta = useMeta()
  const [zoom, setZoom] = useState(ZOOM_MIN)
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const viewportRef = useRef(null)
  const imageRef = useRef(null)
  const fieldBox = hasBox(field) ? field : null
  const focusBox = focus?.box ?? null
  const target = focusBox ?? fieldBox

  useEffect(() => { setFailed(false); setLoaded(false) }, [imageUrl])

  // Bring the highlighted value to the middle of the viewer: computed from the image size, so it works only once the
  // image is loaded (it has no height before) and scrolls just this viewer — never the dialog around it.
  useEffect(() => {
    const viewport = viewportRef.current
    const image = imageRef.current
    if (!viewport || !image || !loaded || !target) return
    viewport.scrollTo({
      left: Math.max(0, (target.x + target.width / 2) * image.clientWidth - viewport.clientWidth / 2),
      top: Math.max(0, (target.y + target.height / 2) * image.clientHeight - viewport.clientHeight / 2),
      behavior: 'smooth',
    })
  }, [loaded, zoom, target?.x, target?.y, target?.width, target?.height])

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
      <div className="flex flex-none items-center justify-between gap-2 px-3 py-2">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          תצוגת מסמך
          {focus ? (
            <span className="mr-2 inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-800 dark:bg-teal-950/40 dark:text-teal-200">
              מוצג: <span dir="ltr" className="font-mono">{focus.value}</span> (לפי {meta.source_labels[focus.box_source]})
              <button type="button" onClick={onClearFocus} aria-label="הסר הדגשה" className="rounded-full p-0.5 hover:bg-teal-100 dark:hover:bg-teal-900"><X size={11} /></button>
            </span>
          ) : fieldBox && field.box_source ? (
            <span className="mr-2 text-xs font-normal text-gray-500 dark:text-gray-400">· מיקום לפי {meta.source_labels[field.box_source] ?? field.box_source}</span>
          ) : field && !fieldBox ? (
            <span className="mr-2 text-xs font-normal text-gray-500 dark:text-gray-400">· אין מיקום לשדה – מוצג העמוד כולו</span>
          ) : null}
        </span>
        <div className="flex items-center gap-1.5">
          <button type="button" aria-label="הקטנת זום" disabled={zoom <= ZOOM_MIN} onClick={() => setZoom((value) => Math.max(ZOOM_MIN, value - ZOOM_STEP))} className="rounded-lg border border-gray-300 bg-white p-1.5 text-gray-600 hover:bg-gray-50 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200">
            <ZoomOut size={16} />
          </button>
          <span className="w-10 text-center text-xs tabular-nums text-gray-500">{Math.round(zoom * 100)}%</span>
          <button type="button" aria-label="הגדלת זום" disabled={zoom >= ZOOM_MAX} onClick={() => setZoom((value) => Math.min(ZOOM_MAX, value + ZOOM_STEP))} className="rounded-lg border border-gray-300 bg-white p-1.5 text-gray-600 hover:bg-gray-50 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200">
            <ZoomIn size={16} />
          </button>
        </div>
      </div>

      <div ref={viewportRef} className="min-h-[260px] flex-1 overflow-auto rounded-b-xl bg-white dark:bg-slate-900" dir="ltr">
        {failed || !imageUrl ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <ImageOff size={22} /> אין תמונה זמינה
          </div>
        ) : (
          <div className="relative" style={{ width: `${zoom * 100}%` }}>
            <img ref={imageRef} src={imageUrl} alt={alt} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} className="block h-auto w-full select-none" draggable={false} />
            {fieldBox && (
              <div
                className={`pointer-events-none absolute rounded-md border-2 border-review-500 bg-review-400/15 transition-all duration-300 ${focusBox ? '' : DIM_PAGE}`}
                style={boxStyle(fieldBox)}
              />
            )}
            {focusBox && (
              <div className={`pointer-events-none absolute rounded-md border-[3px] border-teal-500 bg-teal-400/15 transition-all duration-300 ${DIM_PAGE}`} style={boxStyle(focusBox)}>
                <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-teal-600 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-white shadow">{focus.value}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
