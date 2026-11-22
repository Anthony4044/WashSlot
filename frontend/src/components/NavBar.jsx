import { useSyncExternalStore } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { clearToken, isLoggedIn, isOperator, subscribe } from '../auth.js'

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

function navClass({ isActive }) {
  return isActive ? 'nav-link active' : 'nav-link'
}

export function NavBar() {
  const navigate = useNavigate()
  const loggedIn = useSyncExternalStore(subscribe, isLoggedIn, () => false)
  const operator = useSyncExternalStore(subscribe, isOperator, () => false)

  function logout() {
    clearToken()
    navigate('/login')
  }

  return (
    <header className="nav">
      <NavLink to="/laundromats" className="brand" end>
        <Logo />
        <span className="brand-name">
          Wash<span>Slot</span>
        </span>
      </NavLink>

      <nav aria-label="Main">
        <NavLink to="/laundromats" className={navClass}>
          Laundromats
        </NavLink>
        <NavLink to="/reservations" className={navClass}>
          My reservations
        </NavLink>
        {operator && (
          <>
            <NavLink to="/operator" className={navClass} end>
              Operator
            </NavLink>
            <NavLink to="/operator/today" className={navClass}>
              Today
            </NavLink>
          </>
        )}
        {loggedIn ? (
          <button type="button" className="nav-link nav-button" onClick={logout}>
            Logout
          </button>
        ) : (
          <NavLink to="/login" className={navClass}>
            Login
          </NavLink>
        )}
      </nav>
    </header>
  )
}
