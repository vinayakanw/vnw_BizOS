# Deploying BizOS

Plan: Neon (database, already set up) + Render (API) + Vercel (website).
The website proxies `/api` to the API, so login cookies stay first-party.

1. Push the code to a GitHub repo (without .env).
2. Render: New > Blueprint > pick the repo. Fill DATABASE_URL, LLM_API_KEY, and put
   `https://example.com` in CORS_ORIGINS and PUBLIC_APP_URL for now. Wait for "Live". Copy the API URL.
3. Put that URL in `frontend/vercel.json` (replace YOUR-API-NAME.onrender.com), commit and push.
4. Vercel: Add New Project > same repo > Root Directory `frontend`.
   Environment variable: `VITE_API_URL` = `/api`. Deploy. Copy the site URL.
5. Render > bizos-api > Environment: set CORS_ORIGINS and PUBLIC_APP_URL to the Vercel URL. It redeploys.
6. Open the Vercel URL, register, load the sample shop, open /chat/<your-slug>.

Notes
- Free Render sleeps after 15 minutes idle. The first request after that takes about a minute, and the background
  checks pause while it sleeps. The paid Starter plan removes both.
- The knowledge search model needs about 400 MB of memory. If Render shows "out of memory", use the Starter plan.
- Migrations run on every start (`alembic upgrade head`).
