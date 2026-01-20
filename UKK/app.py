from flask import Flask, render_template, redirect, url_for, session, flash, request, jsonify
import sqlite3
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'rahasia'

DB_NAME = 'db_ukk.db'


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Tabel Users
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'guru'
        )
    ''')

    # 2. Tabel Reservations
    c.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            pic_name TEXT NOT NULL,
            description TEXT,
            reservation_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT DEFAULT 'Terjadwal',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 3. TABEL BARU: LOG IOT (Untuk Sensor Masuk/Keluar)
    c.execute('''
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL, -- 'in' atau 'out'
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Cek Admin Default (Operator)
    c.execute('SELECT * FROM users WHERE username = ?', ('operator',))
    if c.fetchone() is None:
        c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                  ('operator', 'operator@mail.id', 'admin123', 'admin'))
    conn.commit()
    conn.close()


# --- HELPER: Update Status Otomatis ---
def calculate_status(date_str, start_str, end_str):
    now = datetime.now()
    try:
        start_dt = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date_str} {end_str}", "%Y-%m-%d %H:%M")

        if now < start_dt:
            return 'Terjadwal'
        elif start_dt <= now <= end_dt:
            return 'Aktif'
        else:
            return 'Selesai'
    except:
        return 'Terjadwal'


def update_all_reservation_statuses():
    conn = get_db_connection()
    reservations = conn.execute('SELECT * FROM reservations').fetchall()
    for res in reservations:
        new_status = calculate_status(res['reservation_date'], res['start_time'], res['end_time'])
        if res['status'] != new_status:
            conn.execute('UPDATE reservations SET status = ? WHERE id = ?', (new_status, res['id']))
    conn.commit()
    conn.close()


# --- ROUTES ---

@app.route('/')
def index():
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()

        if user:
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau Password salah!', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Berhasil logout.', 'info')
    return redirect(url_for('dashboard'))


# --- DASHBOARD (DATA DARI IOT) ---
@app.route('/dashboard')
def dashboard():
    # Update status jadwal dulu biar real-time
    update_all_reservation_statuses()

    conn = get_db_connection()
    today_str = date.today().strftime('%Y-%m-%d')

    # 1. Hitung Statistik IoT (Pengunjung) Hari Ini
    # Ambil data dari tabel visitor_logs, BUKAN reservations

    # Hitung yang direction='in' (Masuk)
    masuk_today = conn.execute("SELECT COUNT(*) FROM visitor_logs WHERE direction='in' AND date(timestamp) = ?",
                               (today_str,)).fetchone()[0]

    # Hitung yang direction='out' (Keluar)
    keluar_today = conn.execute("SELECT COUNT(*) FROM visitor_logs WHERE direction='out' AND date(timestamp) = ?",
                                (today_str,)).fetchone()[0]

    # Total Aktivitas (Masuk + Keluar)
    total_today = masuk_today + keluar_today

    # 2. Ambil "Reservasi Saya" (Khusus User yang Login)
    my_reservations = []
    if session.get('loggedin'):
        user_id = session['id']
        my_reservations = conn.execute(
            'SELECT * FROM reservations WHERE user_id = ? ORDER BY reservation_date DESC LIMIT 5',
            (user_id,)).fetchall()

    conn.close()

    return render_template('dashboard.html',
                           username=session.get('username'),
                           role=session.get('role'),
                           loggedin=session.get('loggedin'),
                           # Data Statistik IoT
                           total_today=total_today,
                           masuk_today=masuk_today,
                           keluar_today=keluar_today,
                           # Data Tabel Reservasi
                           my_reservations=my_reservations)


# --- API UNTUK ALAT IOT (ESP32/Arduino) ---
# Cara pakai: kirim POST request ke /api/sensor
# Body (JSON): { "direction": "in" } atau { "direction": "out" }
@app.route('/api/sensor', methods=['POST'])
def api_sensor():
    data = request.json
    direction = data.get('direction')  # Harusnya 'in' atau 'out'

    if direction in ['in', 'out']:
        conn = get_db_connection()
        # Simpan waktu sekarang otomatis
        conn.execute('INSERT INTO visitor_logs (direction, timestamp) VALUES (?, ?)',
                     (direction, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"Data {direction} saved"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid direction. Use 'in' or 'out'"}), 400


# --- HELPER BUAT TESTING (Simulasi tanpa alat) ---
@app.route('/test_iot/<direction>')
def test_iot(direction):
    if direction in ['in', 'out']:
        conn = get_db_connection()
        conn.execute('INSERT INTO visitor_logs (direction, timestamp) VALUES (?, ?)',
                     (direction, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        flash(f'Simulasi sensor: Orang {direction} berhasil ditambahkan!', 'info')
    return redirect(url_for('dashboard'))


# --- ROUTE SCHEDULE & RESERVATION ---

@app.route('/schedule')
def schedule():
    update_all_reservation_statuses()
    conn = get_db_connection()
    reservations = conn.execute('SELECT * FROM reservations ORDER BY reservation_date DESC, start_time ASC').fetchall()
    conn.close()
    return render_template('schedule.html', jadwal=reservations, loggedin=session.get('loggedin'),
                           role=session.get('role'), username=session.get('username'))


@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    if not session.get('loggedin'):
        flash('Wajib login untuk reservasi', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        initial_status = calculate_status(request.form['date'], request.form['start_time'], request.form['end_time'])
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO reservations (user_id, pic_name, description, reservation_date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (session['id'], request.form['pic_name'], request.form['description'], request.form['date'],
             request.form['start_time'], request.form['end_time'], initial_status))
        conn.commit()
        conn.close()
        flash('Jadwal berhasil ditambahkan', 'success')
        return redirect(url_for('schedule'))
    return render_template('reservation.html', loggedin=True, role=session.get('role'), username=session.get('username'))


# --- KONFIGURASI HALAMAN USER (ADMIN) ---
@app.route('/user')
def user():
    # Proteksi: Hanya Admin
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    # Ambil semua user
    users = conn.execute('SELECT * FROM users').fetchall()

    # Hitung Statistik User untuk Box di atas tabel
    total_user = len(users)
    count_admin = len([u for u in users if u['role'] == 'admin'])
    count_guru = len([u for u in users if u['role'] == 'guru'])

    conn.close()

    return render_template('user.html',
                           users=users,
                           total_user=total_user,
                           count_admin=count_admin,
                           count_guru=count_guru,
                           loggedin=True,
                           role='admin',
                           username=session.get('username'))


@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
                         (request.form['username'], request.form['email'], request.form['password'],
                          request.form['role']))
            conn.commit()
            conn.close()
            flash('User berhasil ditambahkan', 'success')
            return redirect(url_for('user'))
        except sqlite3.IntegrityError:
            flash('Username sudah ada!', 'danger')
    return render_template('add_user.html', loggedin=True, role='admin', username=session.get('username'))


# --- ROUTE DELETE USER ---
@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    # 1. Proteksi: Hanya Admin yang boleh akses
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    target_user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if target_user:
        # 3. LOGIKA PENTING: Jangan hapus jika username-nya 'operator'
        if target_user['username'] == 'operator':
            flash('ERROR: Akun Super Admin tidak boleh dihapus!', 'danger')
        else:
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            flash(f"User {target_user['username']} berhasil dihapus.", 'success')

    conn.close()
    return redirect(url_for('user'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)