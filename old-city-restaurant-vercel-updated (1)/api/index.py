from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
import sqlite3
import os
import base64

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.environ.get('SECRET_KEY', 'old_city_restaurant_secret_key_2026')

# Google OAuth Client ID (create one at https://console.cloud.google.com/apis/credentials
# and set it as an environment variable named GOOGLE_CLIENT_ID in your Vercel project settings)
GOOGLE_CLIENT_ID = os.environ.get('368495148067-l64usk4mkp9supcm8pj0qq0ftiaekbse.apps.googleusercontent.com', '')

# Use /tmp for SQLite in serverless environment
DATABASE = '/tmp/old_city.db'

# Uploaded images are stored as base64 text directly inside SQLite so they work
# without needing a persistent filesystem (Vercel's filesystem is read-only /
# ephemeral outside of /tmp). Keep uploads reasonably small.
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_IMAGE_BYTES = 3 * 1024 * 1024  # 3 MB


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(cursor, table, column, coltype):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = [row[1] for row in cursor.fetchall()]
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _encode_uploaded_image(file_storage):
    """Reads an uploaded file and returns (base64_str, mimetype), or (None, None)
    if nothing valid was uploaded."""
    if not file_storage or not file_storage.filename:
        return None, None
    if not _allowed_image(file_storage.filename):
        return None, None
    data = file_storage.read()
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None, None
    mimetype = file_storage.mimetype or 'image/jpeg'
    return base64.b64encode(data).decode('utf-8'), mimetype


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            image TEXT,
            is_special INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            guests INTEGER NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            is_approved INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Customers who signed in with Google
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            name TEXT,
            picture TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Physical restaurant tables customers can pick from, with photos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurant_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number TEXT NOT NULL,
            capacity INTEGER NOT NULL DEFAULT 2,
            location TEXT,
            description TEXT,
            image_data TEXT,
            image_mime TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Extend existing tables with new columns needed for table-booking + uploads
    _add_column_if_missing(cursor, 'reservations', 'user_id', 'INTEGER')
    _add_column_if_missing(cursor, 'reservations', 'table_id', 'INTEGER')
    _add_column_if_missing(cursor, 'reservations', 'is_seen', 'INTEGER DEFAULT 0')
    _add_column_if_missing(cursor, 'menu_items', 'image_data', 'TEXT')
    _add_column_if_missing(cursor, 'menu_items', 'image_mime', 'TEXT')
    _add_column_if_missing(cursor, 'restaurant_tables', 'image', 'TEXT')

    # Ingredients (shared list, used to build recipes) and per-dish recipes,
    # so the admin can see food cost and profit margin for each menu item.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'kg',
            cost_per_unit REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipe_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_item_id INTEGER NOT NULL,
            ingredient_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Staff directory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # A simple manual sales log (this site doesn't have a POS/checkout system,
    # so real sales numbers only exist once someone logs them here) — this
    # powers the Reports & Analytics page.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            sale_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("SELECT * FROM admin_users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO admin_users (username, password) VALUES (?, ?)",
            ('admin', 'oldcity2026')
        )

    cursor.execute("SELECT COUNT(*) FROM menu_items")
    if cursor.fetchone()[0] == 0:
        sample_items = [
            ('Uzbek Plov', 'Fragrant rice with tender lamb, carrots, chickpeas, and raisins, slow-cooked in a traditional kazan.', 12.00, 'Main Course', 'plov.jpg', 1),
            ('Lagman Noodles', 'Hand-pulled noodles with beef, vegetables, and aromatic herbs in a rich, flavorful broth.', 10.00, 'Main Course', 'lagman.jpg', 1),
            ('Manti Dumplings', 'Steamed dumplings filled with seasoned lamb and onions, served with tangy yogurt sauce.', 9.00, 'Main Course', 'manti.jpg', 1),
            ('Grilled Meat Platter', 'Marinated meat grilled to perfection, served with fresh vegetables and potatoes.', 18.00, 'Main Course', 'grilled.jpg', 1),
            ('Samsa Pastry', 'Flaky pastry filled with juicy minced meat, baked until golden brown in a clay tandoor.', 4.00, 'Appetizer', 'samsa.jpg', 1),
            ('Traditional Borscht', 'Rich beetroot soup with fresh vegetables, served with sour cream and chili.', 7.00, 'Soup', 'borscht.jpg', 0),
            ('Beef & Vegetable Soup', 'A hearty broth with tender beef, pumpkin, carrots and potatoes, served with a side of vinegar and chili.', 8.00, 'Soup', 'soup.jpg', 0),
            ('Beet Salad', 'Fresh beetroot salad with carrots, herbs, and house dressing.', 5.00, 'Salad', 'beet_salad.jpg', 0),
            ('Fresh Bread', 'Traditional Uzbek non bread baked fresh daily.', 2.00, 'Side', 'bread.jpg', 0),
        ]
        cursor.executemany(
            "INSERT INTO menu_items (name, description, price, category, image, is_special) VALUES (?, ?, ?, ?, ?, ?)",
            sample_items
        )

    cursor.execute("SELECT COUNT(*) FROM restaurant_tables")
    if cursor.fetchone()[0] == 0:
        sample_tables = [
            ('Corner Booth', 2, 'Private Nook', 'A cozy corner booth set for two, perfect for an intimate dinner.', 'table-booth.jpg'),
            ('Dining Room A', 4, 'Main Hall', 'A traditional table in our main dining hall, beneath handwoven wall art.', 'table-dining-a.jpg'),
            ('Dining Room B', 4, 'Main Hall', 'A warm table by the main hall, ideal for family dinners.', 'table-dining-b.jpg'),
            ('Gallery Hall', 6, 'Main Hall', 'A larger table along our carpeted gallery corridor — great for groups.', 'table-hallway.jpg'),
            ('Bar Corner', 2, 'Bar Area', 'Seating right by our fully stocked bar.', 'table-bar.jpg'),
        ]
        cursor.executemany(
            "INSERT INTO restaurant_tables (table_number, capacity, location, description, image) VALUES (?, ?, ?, ?, ?)",
            sample_tables
        )

    cursor.execute("SELECT COUNT(*) FROM ingredients")
    if cursor.fetchone()[0] == 0:
        sample_ingredients = [
            ('Rice', 'kg', 1.20),
            ('Lamb Meat', 'kg', 8.50),
            ('Beef', 'kg', 7.00),
            ('Carrots', 'kg', 0.60),
            ('Onion', 'kg', 0.40),
            ('Chickpeas', 'kg', 2.00),
            ('Raisins', 'kg', 4.00),
            ('Cooking Oil', 'l', 2.50),
            ('Garlic', 'kg', 3.00),
            ('Flour', 'kg', 0.70),
            ('Eggs', 'pcs', 0.15),
            ('Cabbage', 'kg', 0.50),
            ('Beetroot', 'kg', 0.55),
            ('Potato', 'kg', 0.45),
            ('Tomato', 'kg', 1.10),
            ('Cucumber', 'kg', 1.00),
            ('Dill', 'kg', 6.00),
            ('Sour Cream', 'kg', 3.20),
            ('Salt', 'kg', 0.30),
            ('Black Pepper', 'kg', 12.00),
        ]
        cursor.executemany(
            "INSERT INTO ingredients (name, unit, cost_per_unit) VALUES (?, ?, ?)",
            sample_ingredients
        )

        # A worked example so the food-cost feature isn't empty on first load —
        # the admin can edit or delete this and build out the rest of the recipes.
        plov_row = cursor.execute("SELECT id FROM menu_items WHERE name = 'Uzbek Plov'").fetchone()
        if plov_row:
            plov_id = plov_row[0]
            ing_ids = {row[1]: row[0] for row in cursor.execute("SELECT id, name FROM ingredients").fetchall()}
            sample_recipe = [
                (plov_id, ing_ids['Rice'], 0.35),
                (plov_id, ing_ids['Lamb Meat'], 0.25),
                (plov_id, ing_ids['Carrots'], 0.20),
                (plov_id, ing_ids['Onion'], 0.08),
                (plov_id, ing_ids['Chickpeas'], 0.05),
                (plov_id, ing_ids['Raisins'], 0.02),
                (plov_id, ing_ids['Cooking Oil'], 0.05),
                (plov_id, ing_ids['Garlic'], 0.01),
            ]
            cursor.executemany(
                "INSERT INTO recipe_items (menu_item_id, ingredient_id, quantity) VALUES (?, ?, ?)",
                sample_recipe
            )

    conn.commit()
    conn.close()

# Initialize DB on first request
@app.before_request
def before_request():
    init_db()

@app.route('/')
def home():
    conn = get_db()
    specials = conn.execute("SELECT * FROM menu_items WHERE is_special = 1 LIMIT 6").fetchall()
    reviews = conn.execute("SELECT * FROM reviews WHERE is_approved = 1 ORDER BY created_at DESC LIMIT 6").fetchall()
    conn.close()
    return render_template('index.html', specials=specials, reviews=reviews)

@app.route('/menu')
def menu():
    conn = get_db()
    categories = conn.execute("SELECT DISTINCT category FROM menu_items ORDER BY category").fetchall()
    items = conn.execute("SELECT * FROM menu_items ORDER BY category, name").fetchall()
    conn.close()
    return render_template('menu.html', items=items, categories=categories)


# ---------------------------------------------------------------------------
# CUSTOMER GOOGLE LOGIN
# ---------------------------------------------------------------------------

@app.route('/login')
def login():
    if session.get('customer_user_id'):
        return redirect(request.args.get('next') or url_for('reservation'))
    next_url = request.args.get('next', url_for('reservation'))
    return render_template('login.html', google_client_id=GOOGLE_CLIENT_ID, next_url=next_url)


@app.route('/auth/google', methods=['POST'])
def auth_google():
    data = request.get_json(silent=True) or {}
    token = data.get('credential')
    next_url = data.get('next') or url_for('reservation')

    if not token:
        return jsonify(ok=False, error='Missing Google credential.'), 400
    if not GOOGLE_CLIENT_ID:
        return jsonify(ok=False, error='Google Sign-In is not configured on the server yet (missing GOOGLE_CLIENT_ID).'), 500

    try:
        idinfo = google_id_token.verify_oauth2_token(token, google_auth_requests.Request(), GOOGLE_CLIENT_ID)
    except ValueError:
        return jsonify(ok=False, error='We could not verify that Google account. Please try again.'), 401

    google_id = idinfo.get('sub')
    email = idinfo.get('email', '')
    name = idinfo.get('name', email)
    picture = idinfo.get('picture', '')

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()
    if user:
        conn.execute("UPDATE users SET email = ?, name = ?, picture = ? WHERE google_id = ?",
                     (email, name, picture, google_id))
        user_id = user['id']
    else:
        cur = conn.execute("INSERT INTO users (google_id, email, name, picture) VALUES (?, ?, ?, ?)",
                            (google_id, email, name, picture))
        user_id = cur.lastrowid
    conn.commit()
    conn.close()

    session['customer_user_id'] = user_id
    session['customer_name'] = name
    session['customer_email'] = email
    session['customer_picture'] = picture

    return jsonify(ok=True, redirect=next_url)


@app.route('/logout')
def logout():
    session.pop('customer_user_id', None)
    session.pop('customer_name', None)
    session.pop('customer_email', None)
    session.pop('customer_picture', None)
    flash('You have been signed out.', 'success')
    return redirect(url_for('home'))


# ---------------------------------------------------------------------------
# TABLE BOOKING (requires Google sign-in)
# ---------------------------------------------------------------------------

@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    if not session.get('customer_user_id'):
        flash('Please sign in with Google first to reserve a table.', 'error')
        return redirect(url_for('login', next=url_for('reservation')))

    if request.method == 'POST':
        table_id = request.form.get('table_id')
        date = request.form.get('date')
        time = request.form.get('time')
        guests = request.form.get('guests')
        phone = request.form.get('phone', '')
        message = request.form.get('message', '')

        if not all([table_id, date, time, guests, phone]):
            flash('Please fill in phone, date, time, guests and pick a table.', 'error')
            return redirect(url_for('reservation'))

        conn = get_db()
        table = conn.execute("SELECT * FROM restaurant_tables WHERE id = ? AND is_active = 1",
                              (table_id,)).fetchone()
        if not table:
            conn.close()
            flash('That table is not available anymore. Please choose another.', 'error')
            return redirect(url_for('reservation'))

        conflict = conn.execute("""
            SELECT id FROM reservations
            WHERE table_id = ? AND date = ? AND time = ? AND status IN ('pending', 'confirmed')
        """, (table_id, date, time)).fetchone()
        if conflict:
            conn.close()
            flash('Sorry — that table is already booked for the selected time. Please pick another time or table.', 'error')
            return redirect(url_for('reservation'))

        conn.execute("""
            INSERT INTO reservations (name, phone, email, date, time, guests, message, status, is_seen, user_id, table_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
        """, (session.get('customer_name'), phone, session.get('customer_email'), date, time,
              guests, message, session.get('customer_user_id'), table_id))
        conn.commit()
        conn.close()

        flash('Your table request has been sent! The restaurant will confirm shortly.', 'success')
        return redirect(url_for('reservation'))

    conn = get_db()
    tables = conn.execute("SELECT * FROM restaurant_tables WHERE is_active = 1 ORDER BY table_number").fetchall()
    my_reservations = conn.execute("""
        SELECT r.*, t.table_number, t.location AS table_location
        FROM reservations r LEFT JOIN restaurant_tables t ON t.id = r.table_id
        WHERE r.user_id = ? ORDER BY r.created_at DESC LIMIT 10
    """, (session.get('customer_user_id'),)).fetchall()
    conn.close()
    return render_template('reservation.html', tables=tables, my_reservations=my_reservations)


@app.route('/api/tables/availability')
def api_tables_availability():
    if not session.get('customer_user_id'):
        return jsonify(ok=False, error='Not signed in'), 401

    date = request.args.get('date', '')
    time = request.args.get('time', '')

    conn = get_db()
    tables = conn.execute("SELECT * FROM restaurant_tables WHERE is_active = 1 ORDER BY table_number").fetchall()

    busy_ids = set()
    if date and time:
        rows = conn.execute("""
            SELECT table_id FROM reservations
            WHERE date = ? AND time = ? AND status IN ('pending', 'confirmed') AND table_id IS NOT NULL
        """, (date, time)).fetchall()
        busy_ids = {row['table_id'] for row in rows}
    conn.close()

    result = []
    for t in tables:
        if t['image_data']:
            photo_url = url_for('media_table', id=t['id'])
        elif t['image']:
            photo_url = url_for('static', filename='images/' + t['image'])
        else:
            photo_url = ''
        result.append({
            'id': t['id'],
            'table_number': t['table_number'],
            'capacity': t['capacity'],
            'location': t['location'] or '',
            'description': t['description'] or '',
            'has_photo': bool(t['image_data'] or t['image']),
            'image_url': photo_url,
            'status': 'busy' if t['id'] in busy_ids else 'free',
        })
    return jsonify(ok=True, tables=result)


# ---------------------------------------------------------------------------
# IMAGE SERVING (images uploaded via the admin panel are stored in the DB)
# ---------------------------------------------------------------------------

@app.route('/media/menu/<int:id>')
def media_menu(id):
    conn = get_db()
    row = conn.execute("SELECT image_data, image_mime FROM menu_items WHERE id = ?", (id,)).fetchone()
    conn.close()
    if not row or not row['image_data']:
        return '', 404
    return Response(base64.b64decode(row['image_data']), mimetype=row['image_mime'] or 'image/jpeg')


@app.route('/media/table/<int:id>')
def media_table(id):
    conn = get_db()
    row = conn.execute("SELECT image_data, image_mime FROM restaurant_tables WHERE id = ?", (id,)).fetchone()
    conn.close()
    if not row or not row['image_data']:
        return '', 404
    return Response(base64.b64decode(row['image_data']), mimetype=row['image_mime'] or 'image/jpeg')


@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/review', methods=['POST'])
def submit_review():
    name = request.form['name']
    rating = request.form['rating']
    comment = request.form.get('comment', '')

    conn = get_db()
    conn.execute("INSERT INTO reviews (name, rating, comment) VALUES (?, ?, ?)",
                 (name, rating, comment))
    conn.commit()
    conn.close()

    flash('Thank you for your review! It will appear after approval.', 'success')
    return redirect(url_for('home'))

# ADMIN PANEL
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        user = conn.execute("SELECT * FROM admin_users WHERE username = ? AND password = ?",
                           (username, password)).fetchone()
        conn.close()

        if user:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials', 'error')

    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    stats = {
        'total_reservations': conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0],
        'pending_reservations': conn.execute("SELECT COUNT(*) FROM reservations WHERE status = 'pending'").fetchone()[0],
        'total_menu_items': conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0],
        'total_reviews': conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
        'pending_reviews': conn.execute("SELECT COUNT(*) FROM reviews WHERE is_approved = 0").fetchone()[0],
        'total_tables': conn.execute("SELECT COUNT(*) FROM restaurant_tables").fetchone()[0],
    }
    recent_reservations = conn.execute("""
        SELECT r.*, t.table_number FROM reservations r
        LEFT JOIN restaurant_tables t ON t.id = r.table_id
        ORDER BY r.created_at DESC LIMIT 10
    """).fetchall()
    conn.close()

    return render_template('admin/dashboard.html', stats=stats, reservations=recent_reservations)

def _get_food_cost(conn, menu_item_id):
    row = conn.execute("""
        SELECT COALESCE(SUM(ri.quantity * i.cost_per_unit), 0) AS food_cost
        FROM recipe_items ri JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE ri.menu_item_id = ?
    """, (menu_item_id,)).fetchone()
    return row['food_cost'] or 0


@app.route('/admin/menu')
def admin_menu():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    items = conn.execute("""
        SELECT m.*,
               COALESCE((SELECT SUM(ri.quantity * i.cost_per_unit)
                         FROM recipe_items ri JOIN ingredients i ON i.id = ri.ingredient_id
                         WHERE ri.menu_item_id = m.id), 0) AS food_cost,
               (SELECT COUNT(*) FROM recipe_items WHERE menu_item_id = m.id) AS recipe_count
        FROM menu_items m ORDER BY m.category, m.name
    """).fetchall()
    conn.close()
    return render_template('admin/menu.html', items=items)

@app.route('/admin/menu/add', methods=['POST'])
def admin_add_menu():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    name = request.form['name']
    description = request.form['description']
    price = request.form['price']
    category = request.form['category']
    is_special = 1 if request.form.get('is_special') else 0
    image = request.form.get('image', 'default.jpg')

    image_data, image_mime = _encode_uploaded_image(request.files.get('photo'))

    conn = get_db()
    conn.execute("""
        INSERT INTO menu_items (name, description, price, category, image, image_data, image_mime, is_special)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, price, category, image, image_data, image_mime, is_special))
    conn.commit()
    conn.close()

    flash('Menu item added successfully!', 'success')
    return redirect(url_for('admin_menu'))

@app.route('/admin/menu/delete/<int:id>')
def admin_delete_menu(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("DELETE FROM menu_items WHERE id = ?", (id,))
    conn.execute("DELETE FROM recipe_items WHERE menu_item_id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Menu item deleted!', 'success')
    return redirect(url_for('admin_menu'))


# ---------------------------------------------------------------------------
# ADMIN: INGREDIENTS + RECIPES (food cost tracking)
# ---------------------------------------------------------------------------

@app.route('/admin/ingredients')
def admin_ingredients():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    ingredients = conn.execute("""
        SELECT i.*, (SELECT COUNT(*) FROM recipe_items WHERE ingredient_id = i.id) AS used_in
        FROM ingredients i ORDER BY i.name
    """).fetchall()
    conn.close()
    return render_template('admin/ingredients.html', ingredients=ingredients)


@app.route('/admin/ingredients/add', methods=['POST'])
def admin_add_ingredient():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    name = request.form['name']
    unit = request.form.get('unit', 'kg')
    cost_per_unit = request.form.get('cost_per_unit', 0)

    conn = get_db()
    conn.execute("INSERT INTO ingredients (name, unit, cost_per_unit) VALUES (?, ?, ?)",
                 (name, unit, cost_per_unit))
    conn.commit()
    conn.close()

    flash('Ingredient added!', 'success')
    return redirect(url_for('admin_ingredients'))


@app.route('/admin/ingredients/update/<int:id>', methods=['POST'])
def admin_update_ingredient(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    unit = request.form.get('unit', 'kg')
    cost_per_unit = request.form.get('cost_per_unit', 0)

    conn = get_db()
    conn.execute("UPDATE ingredients SET unit = ?, cost_per_unit = ? WHERE id = ?",
                 (unit, cost_per_unit, id))
    conn.commit()
    conn.close()

    flash('Ingredient price updated — every recipe using it is now recalculated.', 'success')
    return redirect(url_for('admin_ingredients'))


@app.route('/admin/ingredients/delete/<int:id>')
def admin_delete_ingredient(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("DELETE FROM ingredients WHERE id = ?", (id,))
    conn.execute("DELETE FROM recipe_items WHERE ingredient_id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Ingredient removed.', 'success')
    return redirect(url_for('admin_ingredients'))


@app.route('/admin/menu/<int:id>/recipe')
def admin_menu_recipe(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    item = conn.execute("SELECT * FROM menu_items WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash('Menu item not found.', 'error')
        return redirect(url_for('admin_menu'))

    recipe_lines = conn.execute("""
        SELECT ri.id, ri.quantity, i.id AS ingredient_id, i.name, i.unit, i.cost_per_unit,
               (ri.quantity * i.cost_per_unit) AS line_cost
        FROM recipe_items ri JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE ri.menu_item_id = ? ORDER BY i.name
    """, (id,)).fetchall()

    all_ingredients = conn.execute("SELECT * FROM ingredients ORDER BY name").fetchall()
    food_cost = _get_food_cost(conn, id)
    conn.close()

    margin_pct = None
    if item['price'] and item['price'] > 0:
        margin_pct = round((item['price'] - food_cost) / item['price'] * 100, 1)

    return render_template('admin/recipe.html', item=item, recipe_lines=recipe_lines,
                            all_ingredients=all_ingredients, food_cost=food_cost, margin_pct=margin_pct)


@app.route('/admin/menu/<int:id>/recipe/add', methods=['POST'])
def admin_add_recipe_item(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    ingredient_id = request.form.get('ingredient_id')
    quantity = request.form.get('quantity')

    if not ingredient_id or not quantity:
        flash('Please choose an ingredient and enter a quantity.', 'error')
        return redirect(url_for('admin_menu_recipe', id=id))

    conn = get_db()
    existing = conn.execute("SELECT id FROM recipe_items WHERE menu_item_id = ? AND ingredient_id = ?",
                             (id, ingredient_id)).fetchone()
    if existing:
        conn.execute("UPDATE recipe_items SET quantity = ? WHERE id = ?", (quantity, existing['id']))
    else:
        conn.execute("INSERT INTO recipe_items (menu_item_id, ingredient_id, quantity) VALUES (?, ?, ?)",
                     (id, ingredient_id, quantity))
    conn.commit()
    conn.close()

    flash('Recipe updated!', 'success')
    return redirect(url_for('admin_menu_recipe', id=id))


@app.route('/admin/recipe-item/delete/<int:recipe_item_id>')
def admin_delete_recipe_item(recipe_item_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    row = conn.execute("SELECT menu_item_id FROM recipe_items WHERE id = ?", (recipe_item_id,)).fetchone()
    conn.execute("DELETE FROM recipe_items WHERE id = ?", (recipe_item_id,))
    conn.commit()
    conn.close()

    flash('Ingredient removed from recipe.', 'success')
    if row:
        return redirect(url_for('admin_menu_recipe', id=row['menu_item_id']))
    return redirect(url_for('admin_menu'))


# ---------------------------------------------------------------------------
# ADMIN: STAFF DIRECTORY
# ---------------------------------------------------------------------------

@app.route('/admin/staff')
def admin_staff():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    staff = conn.execute("SELECT * FROM staff ORDER BY is_active DESC, name").fetchall()
    conn.close()
    return render_template('admin/staff.html', staff=staff)


@app.route('/admin/staff/add', methods=['POST'])
def admin_add_staff():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    name = request.form['name']
    role = request.form['role']
    phone = request.form.get('phone', '')
    notes = request.form.get('notes', '')

    conn = get_db()
    conn.execute("INSERT INTO staff (name, role, phone, notes) VALUES (?, ?, ?, ?)",
                 (name, role, phone, notes))
    conn.commit()
    conn.close()

    flash('Staff member added!', 'success')
    return redirect(url_for('admin_staff'))


@app.route('/admin/staff/update/<int:id>', methods=['POST'])
def admin_update_staff(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    role = request.form.get('role', '')
    phone = request.form.get('phone', '')
    notes = request.form.get('notes', '')

    conn = get_db()
    conn.execute("UPDATE staff SET role = ?, phone = ?, notes = ? WHERE id = ?",
                 (role, phone, notes, id))
    conn.commit()
    conn.close()

    flash('Staff details updated.', 'success')
    return redirect(url_for('admin_staff'))


@app.route('/admin/staff/toggle/<int:id>')
def admin_toggle_staff(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    row = conn.execute("SELECT is_active FROM staff WHERE id = ?", (id,)).fetchone()
    if row:
        conn.execute("UPDATE staff SET is_active = ? WHERE id = ?", (0 if row['is_active'] else 1, id))
        conn.commit()
    conn.close()
    return redirect(url_for('admin_staff'))


@app.route('/admin/staff/delete/<int:id>')
def admin_delete_staff(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("DELETE FROM staff WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Staff member removed.', 'success')
    return redirect(url_for('admin_staff'))


# ---------------------------------------------------------------------------
# ADMIN: REPORTS & ANALYTICS
# ---------------------------------------------------------------------------

@app.route('/admin/reports')
def admin_reports():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()

    total_revenue = conn.execute("""
        SELECT COALESCE(SUM(sl.quantity * m.price), 0) AS total
        FROM sales_log sl JOIN menu_items m ON m.id = sl.menu_item_id
    """).fetchone()['total']

    total_dishes_sold = conn.execute("SELECT COALESCE(SUM(quantity), 0) AS total FROM sales_log").fetchone()['total']

    revenue_by_day = conn.execute("""
        SELECT sl.sale_date AS day, SUM(sl.quantity * m.price) AS revenue
        FROM sales_log sl JOIN menu_items m ON m.id = sl.menu_item_id
        WHERE sl.sale_date >= date('now', '-13 days')
        GROUP BY sl.sale_date ORDER BY sl.sale_date
    """).fetchall()

    top_dishes = conn.execute("""
        SELECT m.name AS name, SUM(sl.quantity) AS qty_sold, SUM(sl.quantity * m.price) AS revenue
        FROM sales_log sl JOIN menu_items m ON m.id = sl.menu_item_id
        GROUP BY m.id ORDER BY qty_sold DESC LIMIT 8
    """).fetchall()

    recent_sales = conn.execute("""
        SELECT sl.id, sl.sale_date, sl.quantity, m.name AS item_name, m.price,
               (sl.quantity * m.price) AS line_total
        FROM sales_log sl JOIN menu_items m ON m.id = sl.menu_item_id
        ORDER BY sl.sale_date DESC, sl.id DESC LIMIT 15
    """).fetchall()

    reservation_stats = conn.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS declined,
               SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending
        FROM reservations
    """).fetchone()

    bookings_by_day = conn.execute("""
        SELECT date(created_at) AS day, COUNT(*) AS count
        FROM reservations
        WHERE created_at >= date('now', '-13 days')
        GROUP BY date(created_at) ORDER BY day
    """).fetchall()

    popular_tables = conn.execute("""
        SELECT t.table_number AS table_number, COUNT(*) AS bookings
        FROM reservations r JOIN restaurant_tables t ON t.id = r.table_id
        GROUP BY r.table_id ORDER BY bookings DESC LIMIT 5
    """).fetchall()

    menu_items = conn.execute("SELECT id, name FROM menu_items ORDER BY category, name").fetchall()
    conn.close()

    return render_template('admin/reports.html',
                            total_revenue=total_revenue,
                            total_dishes_sold=total_dishes_sold,
                            revenue_by_day=revenue_by_day,
                            top_dishes=top_dishes,
                            recent_sales=recent_sales,
                            reservation_stats=reservation_stats,
                            bookings_by_day=bookings_by_day,
                            popular_tables=popular_tables,
                            menu_items=menu_items)


@app.route('/admin/reports/log-sale', methods=['POST'])
def admin_log_sale():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    menu_item_id = request.form.get('menu_item_id')
    quantity = request.form.get('quantity')
    sale_date = request.form.get('sale_date')

    if not all([menu_item_id, quantity, sale_date]):
        flash('Please select a dish, quantity, and date.', 'error')
        return redirect(url_for('admin_reports'))

    conn = get_db()
    conn.execute("INSERT INTO sales_log (menu_item_id, quantity, sale_date) VALUES (?, ?, ?)",
                 (menu_item_id, quantity, sale_date))
    conn.commit()
    conn.close()

    flash('Sale logged!', 'success')
    return redirect(url_for('admin_reports'))


@app.route('/admin/reports/delete-sale/<int:id>')
def admin_delete_sale(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("DELETE FROM sales_log WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Sale entry removed.', 'success')
    return redirect(url_for('admin_reports'))


# ---------------------------------------------------------------------------
# ADMIN: RESTAURANT TABLES (with photo upload)
# ---------------------------------------------------------------------------

@app.route('/admin/tables')
def admin_tables():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    tables = conn.execute("SELECT * FROM restaurant_tables ORDER BY table_number").fetchall()
    conn.close()
    return render_template('admin/tables.html', tables=tables)


@app.route('/admin/tables/add', methods=['POST'])
def admin_add_table():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    table_number = request.form['table_number']
    capacity = request.form.get('capacity', 2)
    location = request.form.get('location', '')
    description = request.form.get('description', '')

    image_data, image_mime = _encode_uploaded_image(request.files.get('photo'))

    conn = get_db()
    conn.execute("""
        INSERT INTO restaurant_tables (table_number, capacity, location, description, image_data, image_mime)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (table_number, capacity, location, description, image_data, image_mime))
    conn.commit()
    conn.close()

    flash('Table added successfully!', 'success')
    return redirect(url_for('admin_tables'))


@app.route('/admin/tables/delete/<int:id>')
def admin_delete_table(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("DELETE FROM restaurant_tables WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Table removed.', 'success')
    return redirect(url_for('admin_tables'))


@app.route('/admin/tables/toggle/<int:id>')
def admin_toggle_table(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    row = conn.execute("SELECT is_active FROM restaurant_tables WHERE id = ?", (id,)).fetchone()
    if row:
        conn.execute("UPDATE restaurant_tables SET is_active = ? WHERE id = ?",
                     (0 if row['is_active'] else 1, id))
        conn.commit()
    conn.close()
    return redirect(url_for('admin_tables'))


@app.route('/admin/reservations')
def admin_reservations():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    reservations = conn.execute("""
        SELECT r.*, t.table_number, t.location AS table_location
        FROM reservations r LEFT JOIN restaurant_tables t ON t.id = r.table_id
        ORDER BY r.date DESC, r.time DESC
    """).fetchall()
    # Mark pending requests as seen now that the admin has opened this page
    conn.execute("UPDATE reservations SET is_seen = 1 WHERE status = 'pending'")
    conn.commit()
    conn.close()
    return render_template('admin/reservations.html', reservations=reservations)

@app.route('/admin/reservation/update/<int:id>/<status>')
def admin_update_reservation(id, status):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("UPDATE reservations SET status = ?, is_seen = 1 WHERE id = ?", (status, id))
    conn.commit()
    conn.close()

    label = 'confirmed' if status == 'confirmed' else 'declined'
    flash(f'Reservation {label}!', 'success')
    return redirect(url_for('admin_reservations'))


@app.route('/admin/api/notifications-count')
def admin_notifications_count():
    if not session.get('admin'):
        return jsonify(count=0)
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM reservations WHERE status = 'pending' AND is_seen = 0").fetchone()[0]
    conn.close()
    return jsonify(count=count)

@app.route('/admin/reviews')
def admin_reviews():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    reviews = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template('admin/reviews.html', reviews=reviews)

@app.route('/admin/review/approve/<int:id>')
def admin_approve_review(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("UPDATE reviews SET is_approved = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Review approved!', 'success')
    return redirect(url_for('admin_reviews'))

@app.route('/admin/review/delete/<int:id>')
def admin_delete_review(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("DELETE FROM reviews WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash('Review deleted!', 'success')
    return redirect(url_for('admin_reviews'))

# Vercel WSGI handler - this is the entry point Vercel expects
# The function name must match the file path pattern
# For api/index.py, Vercel expects a function called 'app' or uses WSGI

if __name__ == '__main__':
    # Only used for local development (e.g. `python api/index.py`)
    app.run(debug=True, port=5000)
