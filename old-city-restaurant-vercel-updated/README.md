# Old City Restaurant — Full-Stack Website

A beautiful, full-stack restaurant website built with Flask and ready for Vercel deployment.

## ✨ What's New

- **Sign in with Google** — customers must sign in with their Google account before they can reserve a table.
- **Visual table booking** — customers pick a date & time, see every table with its photo, capacity and free/reserved status, then reserve the exact table and time they want.
- **Admin photo uploads** — from the admin panel you can upload photos directly from your computer for both menu items and tables (no need to touch code or a file server).
- **Booking notifications** — the admin sidebar shows a live red badge with the number of new table requests, and each new request is tagged "New" until you open the Reservations page. Confirm or Decline each request with one click.

## 🔧 One-time setup: Google Sign-In

Customers sign in with Google, so you need a free Google OAuth Client ID:

1. Go to [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) and create a project (or use an existing one).
2. Click **Create Credentials → OAuth client ID → Web application**.
3. Under **Authorized JavaScript origins**, add your site's URL (e.g. `https://your-site.vercel.app`, and `http://localhost:5000` for local testing).
4. Copy the generated **Client ID**.
5. In your Vercel project, go to **Settings → Environment Variables** and add:
   - `GOOGLE_CLIENT_ID` = the client ID you copied
   - `SECRET_KEY` = any long random string (keeps login sessions secure)
6. Redeploy. Until this is set, the sign-in page will show a message that Google Sign-In isn't configured yet.

## 🚀 Deploy to Vercel

### Step 1: Install Vercel CLI
```bash
npm i -g vercel
```

### Step 2: Login to Vercel
```bash
vercel login
```

### Step 3: Deploy
```bash
cd old-city-restaurant-vercel
vercel --prod
```

Or deploy via Git:
1. Push this folder to a GitHub repository
2. Go to [vercel.com](https://vercel.com)
3. Click "New Project"
4. Import your GitHub repo
5. Add the environment variables above
6. Click "Deploy"

## 📁 Project Structure

```
├── api/
│   └── index.py          ← Flask app (Vercel entry point)
├── static/
│   └── images/           ← Optional fallback photos (uploads now live in the database)
├── templates/
│   ├── index.html        ← Home page
│   ├── menu.html         ← Menu page
│   ├── login.html        ← Google sign-in page
│   ├── reservation.html  ← Table booking page (photos, availability, exact time)
│   ├── contact.html      ← Contact page
│   └── admin/            ← Admin panel templates (dashboard, menu, tables, reservations, reviews)
├── requirements.txt      ← Python dependencies
└── vercel.json          ← Vercel configuration
```

## 📸 Uploading Photos

You no longer need to manually add files to a folder — photos are uploaded straight from the admin panel:

- **Admin → Tables**: add a table's name, capacity, area and a photo, so customers see exactly what they're booking.
- **Admin → Menu Items**: add a dish's name, price, category and a photo.

Supported formats: PNG, JPG, WEBP, GIF (up to ~3MB each).

## 🔑 Admin Access

- **URL:** `your-site.vercel.app/admin`
- **Username:** `admin`
- **Password:** `oldcity2026`

**Change this password** by editing the `admin_users` seed values in `api/index.py`, or by adding a small settings screen — happy to build that too if you want it.

## 🪑 How the Table Booking Works

1. A customer clicks **Reserve Table**, is asked to sign in with Google, then lands on the booking page.
2. They pick a date and time and click **Check Availability** — every table appears with its real photo, capacity, area, and whether it's Free or Reserved for that exact slot.
3. They click **Reserve This Table** on a free table, confirm guest count, phone number and any notes, and submit.
4. You (the admin) see a red notification badge in the sidebar and a "New" tag next to the request in **Admin → Reservations**.
5. You click **Confirm** or **Decline** — the customer can see the updated status under "My Reservation Requests" on the booking page.

## ⚠️ Important Notes for Vercel

1. **SQLite Database:** Vercel uses serverless functions, so the SQLite database (and anything stored in it, including uploaded photos) lives in `/tmp/` which is ephemeral — it can reset on a new deployment or a cold start on a fresh server instance. This was true of the original site too; it's a limitation of running SQLite on serverless hosting, not something specific to the new features.

2. **For real production use, especially once photo uploads matter to you,** consider moving to a persistent database:
   - **Vercel Postgres** (vercel.com/storage/postgres)
   - **Supabase** (free PostgreSQL)
   - **PlanetScale** (free MySQL)
   
   And/or a dedicated image host like **Cloudinary** for the photos. I'm happy to help wire either of these up if you want the data to survive deployments reliably.

## 🛠️ Local Development

```bash
pip install -r requirements.txt
python api/index.py
```

Open http://localhost:5000

## 📞 Contact Info to Update

Edit these in `templates/contact.html` and `templates/index.html`:
- Phone number
- Telegram handle
- Instagram handle
- Google Maps location
- Restaurant address
