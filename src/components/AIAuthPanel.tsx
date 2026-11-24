import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { LogIn, LogOut, ShieldCheck } from 'lucide-react'

export type AIAuthSession = { accessToken: string; email: string }

type AIAuthPanelProps = {
  client: SupabaseClient | null
  onSessionChange: (session: AIAuthSession | null) => void
}

export function AIAuthPanel({ client, onSessionChange }: AIAuthPanelProps) {
  const [session, setSession] = useState<Session | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!client) {
      setLoading(false)
      return
    }

    let mounted = true
    const updateSession = (next: Session | null) => {
      setSession(next)
      onSessionChange(next ? { accessToken: next.access_token, email: next.user.email ?? '' } : null)
    }

    void client.auth.getSession().then(({ data, error: sessionError }) => {
      if (!mounted) return
      if (sessionError) setError('Could not restore your sign-in. Please sign in again.')
      updateSession(data.session)
      setLoading(false)
    })
    const { data: { subscription } } = client.auth.onAuthStateChange((_event, next) => {
      if (!mounted) return
      updateSession(next)
      setLoading(false)
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [client, onSessionChange])

  const signIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!client) return
    setSubmitting(true)
    setError('')
    try {
      const { data, error: signInError } = await client.auth.signInWithPassword({
        email: email.trim(),
        password,
      })
      if (signInError) throw signInError
      setPassword('')
      if (data.session) {
        setSession(data.session)
        onSessionChange({ accessToken: data.session.access_token, email: data.session.user.email ?? '' })
      }
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : 'Could not sign in. Check your email and password.')
    } finally {
      setSubmitting(false)
    }
  }

  const signOut = async () => {
    if (!client) return
    setSubmitting(true)
    setError('')
    const { error: signOutError } = await client.auth.signOut()
    if (signOutError) setError('Could not sign out cleanly. Please try again.')
    setSubmitting(false)
  }

  return (
    <section className="panel ai-auth-panel" aria-label="Sign in for OpenAI analysis">
      <div className="ai-auth-icon"><ShieldCheck size={17} /></div>
      <div className="ai-auth-content">
        <div className="ai-auth-heading">
          <div><h3>Private AI access</h3><p>Sign in with the Supabase account approved for this MarketPulse API.</p></div>
          {session && <span className="status-pill status-active">Signed in</span>}
        </div>
        {!client ? (
          <div className="analysis-error" role="status">
            Supabase sign-in needs <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> in the Vercel frontend settings.
          </div>
        ) : loading ? (
          <p className="ai-auth-hint">Checking your sign-in…</p>
        ) : session ? (
          <div className="ai-auth-session">
            <span>{session.user.email}</span>
            <button className="btn btn-secondary" onClick={() => void signOut()} disabled={submitting}>
              <LogOut size={14} /> {submitting ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        ) : (
          <form className="ai-auth-form" onSubmit={event => void signIn(event)}>
            <label>Email<input type="email" autoComplete="username" required value={email} onChange={event => setEmail(event.target.value)} /></label>
            <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>
            <button className="btn btn-secondary" type="submit" disabled={submitting}>
              <LogIn size={14} /> {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}
        {!session && client && !loading && <p className="ai-auth-hint">Use an account created in Supabase Authentication → Users. Only allowlisted email addresses can run AI analysis.</p>}
        {error && <div className="analysis-error" role="alert">{error}</div>}
      </div>
    </section>
  )
}
