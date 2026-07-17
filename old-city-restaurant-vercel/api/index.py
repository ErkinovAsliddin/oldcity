from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os

# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.environ.get('SECRET_KEY', 'old_city_restaurant_secret_key_2026')

# Use /tmp for SQLite in serverless environment
DATABASE = '/tmp/old_city.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

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
            ('Grilled Lamb Chops', 'Marinated lamb grilled to perfection, served with fresh vegetables and potatoes.', 18.00, 'Main Course', 'grilled.jpg', 1),
            ('Samsa Pastry', 'Flaky pastry filled with juicy minced meat, baked until golden brown in a clay tandoor.', 4.00, 'Appetizer', 'samsa.jpg', 1),
            ('Traditional Borscht', 'Rich beetroot soup with fresh vegetables, served with sour cream and crusty bread.', 7.00, 'Soup', 'borscht.jpg', 0),
            ('Beet Salad', 'Fresh beetroot salad with carrots, herbs, and house dressing.', 5.00, 'Salad', 'beet_salad.jpg', 0),
            ('Fresh Bread', 'Traditional Uzbek non bread baked fresh daily.', 2.00, 'Side', 'bread.jpg', 0),
        ]
        cursor.executemany(
            "INSERT INTO menu_items (name, description, price, category, image, is_special) VALUES (?, ?, ?, ?, ?, ?)",
            sample_items
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

@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form.get('email', '')
        date = request.form['date']
        time = request.form['time']
        guests = request.form['guests']
        message = request.form.get('message', '')

        conn = get_db()
        conn.execute("""
            INSERT INTO reservations (name, phone, email, date, time, guests, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, phone, email, date, time, guests, message))
        conn.commit()
        conn.close()

        flash('Reservation request submitted successfully! We will contact you soon.', 'success')
        return redirect(url_for('reservation'))

    return render_template('reservation.html')

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
    }
    recent_reservations = conn.execute(
        "SELECT * FROM reservations ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    return render_template('admin/dashboard.html', stats=stats, reservations=recent_reservations)

@app.route('/admin/menu')
def admin_menu():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    items = conn.execute("SELECT * FROM menu_items ORDER BY category, name").fetchall()
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

    conn = get_db()
    conn.execute("""
        INSERT INTO menu_items (name, description, price, category, image, is_special)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, description, price, category, image, is_special))
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
    conn.commit()
    conn.close()

    flash('Menu item deleted!', 'success')
    return redirect(url_for('admin_menu'))

@app.route('/admin/reservations')
def admin_reservations():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    reservations = conn.execute("SELECT * FROM reservations ORDER BY date DESC, time DESC").fetchall()
    conn.close()
    return render_template('admin/reservations.html', reservations=reservations)

@app.route('/admin/reservation/update/<int:id>/<status>')
def admin_update_reservation(id, status):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    conn.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()

    flash(f'Reservation {status}!', 'success')
    return redirect(url_for('admin_reservations'))

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
