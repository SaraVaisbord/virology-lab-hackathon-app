import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

/** Sample data for development only: never part of a production build, never mixed with real data. */
async function loadSample() {
  if (import.meta.env.DEV) {
    const { CORRECTION_INSIGHTS_SAMPLE } = await import('../dev/correctionInsightsSample')
    return CORRECTION_INSIGHTS_SAMPLE
  }
  throw new Error('נתוני דוגמה זמינים רק בסביבת פיתוח')
}

/**
 * GET /insights/corrections for a period (and optionally one field). Out-of-date responses are ignored; the last
 * result stays on screen while a new one loads, so a refetch doesn't flash the page — but never across sources:
 * sample data is not shown while real data loads, nor the other way round.
 */
export function useCorrectionInsights({ since, fieldName, sample = false }) {
  const [loaded, setLoaded] = useState(null) // { sample, data }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const requestId = useRef(0)

  const load = useCallback(async () => {
    const id = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const result = sample ? await loadSample() : await api.getCorrectionInsights({ since, fieldName })
      if (id === requestId.current) setLoaded({ sample, data: result })
    } catch (err) {
      if (id === requestId.current) setError(err.message)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [since, fieldName, sample])

  useEffect(() => { load() }, [load])

  return { data: loaded?.sample === sample ? loaded.data : null, loading, error, reload: load }
}
