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
