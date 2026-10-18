import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

// מחסנית מודאלים: רק העליון מגיב למקלדת
const modalStack = []

export default function ModalShell({ title, icon: Icon, onClose, children, footer, maxWidth = 'max-w-lg' }) {
  const modalRef = useRef(null)
  const lastFocusedRef = useRef(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const id = Symbol('modal')
    modalStack.push(id)
    const isTop = () => modalStack[modalStack.length - 1] === id

    lastFocusedRef.current = document.activeElement

    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

    const handleKeyDown = (e) => {
      if (!isTop()) return

      if (e.key === 'Escape') {
        onCloseRef.current?.()
        return
      }

      if (e.key !== 'Tab' || !modalRef.current) return
      const focusableElements = Array.from(modalRef.current.querySelectorAll(focusableSelector)).filter((el) => !el.disabled)
      if (!focusableElements.length) {
        e.preventDefault()
        return
      }
      const first = focusableElements[0]
      const last = focusableElements[focusableElements.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    const focusTimer = setTimeout(() => {
      if (!isTop()) return
      const focusable = modalRef.current?.querySelectorAll(focusableSelector)
      if (focusable && focusable.length > 0) focusable[0].focus()
    }, 50)

    return () => {
      clearTimeout(focusTimer)
      window.removeEventListener('keydown', handleKeyDown)
      const index = modalStack.indexOf(id)
      if (index !== -1) modalStack.splice(index, 1)
      lastFocusedRef.current?.focus?.()
    }
  }, [])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/40 dark:bg-black/60 animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={modalRef}
        className={`flex max-h-[calc(100vh-48px)] flex-col bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full ${maxWidth} animate-slide-up`}
        dir="rtl"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between px-[30px] py-6 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2.5">
            {Icon && <Icon size={22} className="text-pink-500" />}
            <h2 className="text-lg font-bold text-navy-800 dark:text-gray-100">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn-ghost p-2.5 text-gray-600"
            aria-label="סגור חלון"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-[30px] py-[26px] space-y-5">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex shrink-0 items-center justify-end gap-4 px-[30px] py-5 border-t border-gray-100 dark:border-gray-800">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}