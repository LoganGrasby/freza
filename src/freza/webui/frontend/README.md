# freza webui frontend

Vue + Vite + Tailwind implementation for the freza web UI.

## Development

```bash
cd webui/frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:7888`.

## Production build

```bash
cd webui/frontend
npm install
npm run build
```

Build output is written to `webui/dist` and served by the Python web UI server.
