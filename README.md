# GovPilot

This repository contains the existing React dashboard and a single-file Flask API backed by PostgreSQL. The API does not seed demo records; challenges, proposals, pilots, evaluations, files, and workflow decisions are persisted in the configured database.

## Backend

1. Create a PostgreSQL database and copy `.env.example` to `.env`.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Start the API with `flask --app app run --debug` (or `python app.py`). It listens on port `5000` by default.

`app.py` creates the required tables on startup. Registration creates an `officer` account for this application flow. In production, replace open officer registration with invite or approval-based provisioning. Authentication uses 12-hour JWTs.

The API is available under `/api`: authentication, CRUD resources, `/analytics`, dynamic pilot scorecards, procurement readiness, shortlist persistence, and multipart evidence uploads. Local frontend development uses the Vite `/api` proxy, so no frontend API URL is required. For a separately deployed backend, set `VITE_API_BASE_URL` to its public `/api` origin. Set `CORS_ORIGINS` as a comma-separated allowlist only when the browser calls that backend directly.

## Frontend

Run `npm install`, then `npm run dev`. Vite proxies `/api` to `http://localhost:5000` during development.

## Original template notes

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
