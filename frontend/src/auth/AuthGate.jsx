import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { KeyRound, Loader2, Mail } from 'lucide-react'
import { AUTH_REQUIRED_EVENT, api } from '../api'

const CODE_LENGTH = 6
const AuthContext = createContext({ enabled: false, logout: () => {} })

function LoginScreen({ email, askEmail, onLoggedIn }) {
  const [step, setStep] = useState('request') // request → verify
  const [address, setAddress] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sentTo, setSentTo] = useState(email)

  const run = async (action) => {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const sendCode = (event) => {
    event?.preventDefault()
    run(async () => {
      const result = await api.requestLoginCode(askEmail ? address : null)
      setSentTo(result.email)
      setCode('')
      setStep('verify')
    })
  }
  const verify = (event) => {
    event.preventDefault()
    run(async () => {
      await api.verifyLoginCode(code)
      onLoggedIn()
    })
  }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-surface-page p-4 dark:bg-slate-950" dir="rtl">
      <div className="card w-full max-w-sm space-y-4 rounded-xl p-6">
        <div className="flex items-center gap-3">
          <img src="/logos/virus-lab.png" alt="" className="h-10 object-contain" onError={(event) => { event.target.style.display = 'none' }} />
          <div>
            <p className="text-xs text-gray-400">מערכת אימות טפסים</p>
            <h1 className="text-base font-bold text-navy-800 dark:text-gray-100">כניסה למערכת</h1>
          </div>
        </div>

        {step === 'request' ? (
          <form onSubmit={sendCode} className="space-y-3">
            {askEmail ? (
              <label className="block space-y-1 text-sm text-gray-600 dark:text-gray-300">
                <span>כתובת מייל</span>
                <input
                  type="email"
                  required
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  autoComplete="email"
                  autoFocus
                  dir="ltr"
                  placeholder="name@example.org"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-navy-800 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-100"
                />
              </label>
            ) : (
              <p className="text-sm text-gray-600 dark:text-gray-300">
                קוד כניסה חד-פעמי יישלח לתיבת המייל של המעבדה{sentTo ? <> (<span dir="ltr">{sentTo}</span>)</> : null}.
              </p>
            )}
            <button type="submit" className="btn-primary inline-flex w-full items-center justify-center gap-2" disabled={busy || (askEmail && !address)}>
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Mail size={16} />} שלחו לי קוד
            </button>
          </form>
        ) : (
          <form onSubmit={verify} className="space-y-3">
            <p className="text-sm text-gray-600 dark:text-gray-300">
              נשלח קוד בן {CODE_LENGTH} ספרות ל-<span dir="ltr">{sentTo}</span>. הקוד תקף לזמן קצר ולשימוש אחד.
            </p>
            <input
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              dir="ltr"
              aria-label="קוד כניסה"
              placeholder={'•'.repeat(CODE_LENGTH)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-center text-xl tracking-[0.5em] text-navy-800 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-100"
            />
            <button type="submit" className="btn-primary inline-flex w-full items-center justify-center gap-2" disabled={busy || code.length !== CODE_LENGTH}>
              {busy ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />} כניסה
            </button>
            <button type="button" className="btn-ghost w-full text-sm" onClick={sendCode} disabled={busy}>שלחו קוד חדש</button>
          </form>
        )}

        {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
      </div>
    </div>
  )
}

/** Shows the login screen until the server says this browser is logged in (or login is off). */
export function AuthGate({ children }) {
  const [status, setStatus] = useState(null) // { enabled, authenticated, email }
  const [error, setError] = useState('')

  const check = useCallback(() => {
    api.getAuthStatus().then(setStatus).catch((err) => setError(err.message))
  }, [])
  useEffect(() => { check() }, [check])
  useEffect(() => {
    const onRequired = () => setStatus((current) => (current ? { ...current, authenticated: false } : current))
    window.addEventListener(AUTH_REQUIRED_EVENT, onRequired)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onRequired)
  }, [])

  const logout = useCallback(async () => {
    await api.logout().catch(() => {})
    window.location.reload()
  }, [])

  if (error && !status) {
    return <div className="flex h-screen items-center justify-center p-6 text-center text-sm text-red-700" dir="rtl">לא ניתן להתחבר לשרת: {error}</div>
  }
  if (!status) return <div className="flex h-screen items-center justify-center text-sm text-gray-500" dir="rtl">טוען...</div>
  if (!status.authenticated) return <LoginScreen email={status.email} askEmail={status.ask_email} onLoggedIn={check} />
  return <AuthContext.Provider value={{ enabled: status.enabled, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
