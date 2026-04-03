import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import App from './App.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN || ''
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID || ''
const audience = import.meta.env.VITE_AUTH0_AUDIENCE || ''

const authEnabled = !!(domain && clientId)
console.log('[MAIN] Auth0 domain:', domain, 'clientId:', clientId?.slice(0,8), 'enabled:', authEnabled)

const root = createRoot(document.getElementById('root'))

if (authEnabled) {
  root.render(
    <StrictMode>
      <Auth0Provider
        domain={domain}
        clientId={clientId}
        authorizationParams={{
          redirect_uri: window.location.origin,
          audience: audience || undefined,
        }}
      >
        <App authEnabled />
      </Auth0Provider>
    </StrictMode>,
  )
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
