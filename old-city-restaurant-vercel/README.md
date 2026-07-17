# Old City Restaurant — Full-Stack Website

A beautiful, full-stack restaurant website built with Flask and ready for Vercel deployment.

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
5. Click "Deploy"

## 📁 Project Structure

```
├── api/
│   └── index.py          ← Flask app (Vercel entry point)
├── static/
│   └── images/           ← Upload your 20 photos here
├── templates/
│   ├── index.html        ← Home page
│   ├── menu.html         ← Menu page
│   ├── reservation.html  ← Reservation form
│   ├── contact.html      ← Contact page
│   └── admin/            ← Admin panel templates
├── requirements.txt      ← Python dependencies
└── vercel.json          ← Vercel configuration
```

## 📸 Add Your Photos

1. Upload your 20 photos to `static/images/`
2. Name them:
   - `plov.jpg`, `lagman.jpg`, `samsa.jpg`, `manti.jpg`
   - `grilled.jpg`, `borscht.jpg`, `beet_salad.jpg`, `bread.jpg`
   - And any other dish/interior photos

## 🔑 Admin Access

- **URL:** `your-site.vercel.app/admin`
- **Username:** `admin`
- **Password:** `oldcity2026`

## ⚠️ Important Notes for Vercel

1. **SQLite Database:** Vercel uses serverless functions, so the SQLite database resets on each deployment. Data is stored in `/tmp/` which is ephemeral.

2. **For Production:** Consider using:
   - **Vercel Postgres** (vercel.com/storage/postgres)
   - **Supabase** (free PostgreSQL)
   - **PlanetScale** (free MySQL)

3. **Images:** Upload to a CDN like Cloudinary or Imgur for better performance.

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
