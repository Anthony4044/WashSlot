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

The API helper is `src/api.js`: it uses `VITE_API_BASE_URL`, sends `Authorization: Bearer <token>` from storage, and turns `{ "error": "<code>" }` bodies into readable messages.

## Build

```bash
npm run build
```
