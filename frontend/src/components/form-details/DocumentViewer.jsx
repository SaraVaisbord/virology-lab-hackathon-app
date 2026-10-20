import { useEffect, useRef, useState } from 'react'
import { ImageOff, ZoomIn, ZoomOut } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

const ZOOM_MIN = 1
const ZOOM_MAX = 3
const ZOOM_STEP = 0.5
const HIGHLIGHT_PADDING = 0.006 // a little breathing room around the value (normalized units)

const hasBox = (field) => [field?.x, field?.y, field?.width, field?.height].every((value) => typeof value === 'number')

/** Page image with the active field highlighted. Field coordinates are normalized (0..1) to the image. */
export default function DocumentViewer({ imageUrl, field, alt }) {
  const meta = useMeta()
  const [zoom, setZoom] = useState(ZOOM_MIN)
  const [failed, setFailed] = useState(false)
  const highlightRef = useRef(null)
  const box = hasBox(field) ? field : null

  useEffect(() => { setFailed(false) }, [imageUrl])

  useEffect(() => {
    highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })
  }, [box?.id, zoom])

  const pct = (value) => `${(value * 100).toFixed(2)}%`

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
      <div className="flex flex-none items-center justify-between gap-2 px-3 py-2">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          תצוגת מסמך
          {box && field.box_source && (
            <span className="mr-2 text-xs font-normal text-gray-500 dark:text-gray-400">· מיקום לפי {meta.source_labels[field.box_source] ?? field.box_source}</span>
          )}
          {field && !box && <span className="mr-2 text-xs font-normal text-gray-500 dark:text-gray-400">· אין מיקום לשדה – מוצג העמוד כולו</span>}
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

      <div className="min-h-[260px] flex-1 overflow-auto rounded-b-xl bg-white dark:bg-slate-900" dir="ltr">
        {failed || !imageUrl ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <ImageOff size={22} /> אין תמונה זמינה
          </div>
        ) : (
          <div className="relative" style={{ width: `${zoom * 100}%` }}>
            <img src={imageUrl} alt={alt} onError={() => setFailed(true)} className="block h-auto w-full select-none" draggable={false} />
            {box && (
              <div
                ref={highlightRef}
                className="pointer-events-none absolute rounded-md border-2 border-review-500 bg-review-400/15 shadow-[0_0_0_9999px_rgba(15,23,42,0.28)] transition-all duration-300"
                style={{
                  left: pct(Math.max(0, box.x - HIGHLIGHT_PADDING)),
                  top: pct(Math.max(0, box.y - HIGHLIGHT_PADDING)),
                  width: pct(box.width + HIGHLIGHT_PADDING * 2),
                  height: pct(box.height + HIGHLIGHT_PADDING * 2),
                }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
