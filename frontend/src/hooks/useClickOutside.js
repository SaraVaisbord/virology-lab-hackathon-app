import { useEffect, useRef } from 'react'

/** Calls onOutside when a click or Escape happens outside the returned ref's element. */
export function useClickOutside(onOutside, enabled = true) {
  const ref = useRef(null)
  const handlerRef = useRef(onOutside)
  handlerRef.current = onOutside

  useEffect(() => {
    if (!enabled) return undefined
    const onPointer = (event) => {
      if (ref.current && !ref.current.contains(event.target)) handlerRef.current()
    }
    const onKey = (event) => { if (event.key === 'Escape') handlerRef.current() }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [enabled])

  return ref
}
