import { useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { setTokenGetter } from '../api'

export default function AuthGate({ enabled, children }) {
  if (!enabled) return children
  return <AuthGateInner>{children}</AuthGateInner>
}

function AuthGateInner({ children }) {
  const { isAuthenticated, isLoading, loginWithRedirect, logout, user, getAccessTokenSilently } = useAuth0()

  useEffect(() => {
    console.log('[AUTH GATE] isAuthenticated:', isAuthenticated)
    if (isAuthenticated) {
      setTokenGetter(async () => {
        try {
          const token = await getAccessTokenSilently({
            authorizationParams: {
              audience: import.meta.env.VITE_AUTH0_AUDIENCE || undefined,
            },
          })
          console.log('[AUTH GATE] Got token:', token?.slice(0, 20) + '...')
          return token
        } catch (e) {
          console.error('[AUTH GATE] getAccessTokenSilently failed:', e)
          return null
        }
      })
    } else {
      setTokenGetter(null)
    }
  }, [isAuthenticated, getAccessTokenSilently])

  if (isLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="auth-login">
        <div className="auth-card">
          <h1 className="auth-title">Deal Finder</h1>
          <p className="auth-subtitle">Sign in to access your dashboard</p>
          <button className="auth-btn" onClick={() => loginWithRedirect()}>
            Sign in with Google
          </button>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="auth-user-bar">
        <span className="auth-user-name">{user?.name || user?.email}</span>
        <button
          className="auth-logout"
          onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        >
          Sign out
        </button>
      </div>
      {children}
    </>
  )
}
