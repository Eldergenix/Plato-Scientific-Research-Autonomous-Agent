# Plato Dashboard Frontend

This is the Next.js frontend for Plato's research dashboard. It pairs with the FastAPI backend in `dashboard/backend` and powers the hosted Plato demo.

- Live demo: [plato-production-9fea.up.railway.app](https://plato-production-9fea.up.railway.app)
- Repository: [Eldergenix/Plato-Scientific-Research-Autonomous-Agent](https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent)

## Development

```bash
npm install
npm run dev
```

Open the printed local URL, usually `http://localhost:3000`. The frontend expects the dashboard backend at `http://127.0.0.1:7878` unless configured otherwise.

## Verification

```bash
npx tsc --noEmit
npx playwright test
```

## Production

The production deployment is served at:

```text
https://plato-production-9fea.up.railway.app
```
