import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useMeta } from '../meta/MetaContext'

/**
 * Server-side paged form list ("load more"), plus the processing summary.
 * While forms are still in the extraction queue, both are polled so rows update on their own.
 */
export function useForms(filters) {
  const { page_size: pageSize, poll_interval_ms: pollInterval } = useMeta()
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(0)
  const loadedCount = useRef(pageSize)

  // Reload the rows currently on screen (keeps "load more" progress), ignoring out-of-date responses.
  const refresh = useCallback(async ({ reset = false } = {}) => {
    const id = ++requestId.current
    if (reset) {
      loadedCount.current = pageSize
      setLoading(true)
    }
    try {
      const [page, nextSummary] = await Promise.all([
        api.listForms(filters, { limit: loadedCount.current, offset: 0 }),
        api.getSummary(),
      ])
      if (id !== requestId.current) return
      setItems(page.items)
      setTotal(page.total)
      setSummary(nextSummary)
      setError('')
    } catch (err) {
      if (id === requestId.current) setError(err.message)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [filters, pageSize])

  useEffect(() => { refresh({ reset: true }) }, [refresh])

  const loadMore = useCallback(async () => {
    if (loadingMore || items.length >= total) return
    setLoadingMore(true)
    const id = requestId.current
    try {
      const page = await api.listForms(filters, { limit: pageSize, offset: items.length })
      if (id !== requestId.current) return
      setItems((current) => [...current, ...page.items])
      setTotal(page.total)
      loadedCount.current = items.length + page.items.length
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingMore(false)
    }
  }, [filters, items.length, loadingMore, pageSize, total])

  // Poll only while the queue can actually make progress (not when it's disabled on the server).
  const isProcessing = (summary?.pending ?? 0) > 0 && summary?.queue?.pause_reason !== 'disabled'
  useEffect(() => {
    if (!isProcessing) return undefined
    const timer = setInterval(() => refresh(), pollInterval)
    return () => clearInterval(timer)
  }, [isProcessing, pollInterval, refresh])

  /** Replace one row in place after it changed (e.g. a field was approved). */
  const updateItem = useCallback((form) => {
    setItems((current) => current.map((item) => (item.id === form.id ? form : item)))
  }, [])

  return { items, total, summary, loading, loadingMore, error, hasMore: items.length < total, loadMore, refresh, updateItem }
}
