# MediFind MVP

Flask marketplace prototype for finding medicine availability at nearby pharmacies. Customer search shows verified shops, stock, distance, current listed price, and informational same-salt matches. Shopkeepers have protected accounts and manage their own shop inventory. Admins manage accounts and pharmacy verification.

## Local setup

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` values, then start the app with `python app.py`. The first local startup creates/updates the SQLite schema and seeds demo data. Local demo admin credentials are `admin@medifind.local` / `Admin@12345` unless `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set before first startup. Change these before sharing the app.

## Neon + Vercel deployment

1. Create a Neon Postgres project. Copy the **pooled** connection string from Neon. The app accepts `postgresql://` and selects Psycopg 3; the pooled Neon hostname includes `-pooler`.
2. In `.env`, temporarily set `DATABASE_URL` to the Neon connection URL, `DB_SEED_DEMO=0`, `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD`. Initialize the production schema once from your computer:

   ```powershell
   flask --app app init-db
   ```

   This command adds the current tables and image columns. Keep database initialization out of Vercel request startup.
3. In Vercel, import this folder/repository as a project and add environment variables for Production (and Preview if needed): `DATABASE_URL` (Neon pooled URL), `SECRET_KEY` (long random value), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and the three Cloudinary variables below. `DB_SEED_DEMO` should be `0` in production.
4. Deploy from Vercel. `app.py` is the Flask entrypoint, and `public/style.css` is served as a Vercel static asset. Vercel's Python runtime packages the app from `requirements.txt`.

## Cloudinary medicine photos

Create a Cloudinary account and put `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` into local `.env` and Vercel settings. Shopkeepers can then upload a JPG, PNG, or WEBP product photo (up to 5 MB) when adding/updating an inventory listing. The server validates the image, uploads it to the `medifind/medicines` folder, and stores the secure delivery URL and public ID in Postgres. The API secret is used only server-side.

## Routes

- `/` and `/search`: customer pages; optional browser location is requested from the top navigation.
- `/register`, `/login`, `/logout`: customer and shopkeeper account flows. Shopkeeper registration creates a pharmacy pending review.
- `/shop`: authenticated shopkeeper inventory/photo management, scoped to their own pharmacy.
- `/admin`: authenticated account and pharmacy moderation.
- `/api/medicine/<id>` and `/api/health`: JSON detail and database-health endpoints.
- `flask --app app init-db`: create/update schema and initialize the first admin account.

## Notes

The app does not accept orders/payments. Pharmacy coordinates and inventory are supplied by shops. Salt suggestions are text matches, not medical substitution advice; customers should confirm availability and suitability with a pharmacist or clinician. Never commit `.env` or put Cloudinary's secret in browser code.
