# WashSlot front end

Vite · React · React Router.

## Setup (once)

```bash
cd frontend
npm install
```

Copy `.env.example` to `.env` only if you need a different API URL. The default is `http://localhost:8000`.

## Run

```bash
npm run dev   # http://localhost:5173
```

Every route is stubbed. Fill in the page you own under `src/pages/`. Add new routes as one line in `src/App.jsx`.

## Navigation bar

`src/components/NavBar.jsx` sits on every page via `Layout`:

- **Laundromats** → `/laundromats`
- **My reservations** → `/reservations`
- **Login** → `/login` when logged out · **Logout** clears the token and goes to `/login`

Login/Logout flips from the JWT in `src/auth.js` (set by the login page later).

## API client (`src/api.js`)

```js
import { api, ApiError } from './api.js'
import { setToken } from './auth.js'

setToken(tokenFromLogin) // later requests send Authorization: Bearer …

try {
  const data = await api('/laundromats')
  // …
} catch (err) {
  if (err instanceof ApiError) {
    // err.message is readable; err.code is the server's {"error":"…"} value
  }
}
```

- Base URL: `VITE_API_BASE_URL` (default `http://localhost:8000`)
- Token: read from storage via `src/auth.js`
- Errors: `{"error":"<code>"}` → `ApiError` with a readable `message`
- On **401**, the token is cleared and the browser goes to `/login`

## Build

```bash
npm run build
```
