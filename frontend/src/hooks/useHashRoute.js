import { useEffect, useState } from 'react'

// The app's screens, by URL hash (#/insights) — enough for two screens without a router library.
export const ROUTES = { forms: '#/', insights: '#/insights' }

function currentRoute() {
  return Object.keys(ROUTES).find((key) => ROUTES[key] === window.location.hash) ?? 'forms'
}

export function useHashRoute() {
  const [route, setRoute] = useState(currentRoute)
  useEffect(() => {
    const update = () => setRoute(currentRoute())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return route
}
