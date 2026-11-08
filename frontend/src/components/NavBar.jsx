import { useSyncExternalStore } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { clearToken, isLoggedIn, subscribe } from '../auth.js'

function Logo() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="currentColor" />
      <circle cx="16" cy="18" r="8" fill="none" stroke="#f3efe6" strokeWidth="2" />
      <circle cx="16" cy="18" r="3.2" fill="#2a9d8f" />
      <circle cx="11" cy="8" r="1.3" fill="#f3efe6" />
      <circle cx="16" cy="8" r="1.3" fill="#f3efe6" />
    </svg>
  )
}

export function NavBar() {
  const navigate = useNavigate()
  const loggedIn = useSyncExternalStore(subscribe, isLoggedIn, () => false)

  function logout() {
    clearToken()
    navigate('/login')
  }

  return (
    <header className="nav">
      <NavLink to="/laundromats" className="brand">
        <Logo />
        <span>
          Wash<span>Slot</span>
        </span>
      </NavLink>
      <nav>
        <NavLink to="/laundromats">Laundromats</NavLink>
        <NavLink to="/reservations">My reservations</NavLink>
        {loggedIn ? (
          <button type="button" className="nav-button" onClick={logout}>
            Logout
          </button>
        ) : (
          <NavLink to="/login">Login</NavLink>
        )}
      </nav>
    </header>
  )
}
