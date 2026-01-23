from flask import Flask, render_template, redirect, url_for, session, flash, request, jsonify
import sqlite3
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'rahasia'

DB_NAME = 'db_ukk.db'


# --- KONEKSI DATABASE ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# --- INISIALISASI DATABASE (JALAN PERTAMA KALI) ---
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

    # 2. Tabel Reservations (UPDATE STRUKTUR)
    # - Status Default: 'Menunggu' (Agar masuk inbox admin dulu)
    # - rejection_reason: Untuk menyimpan alasan penolakan
    c.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            pic_name TEXT NOT NULL,
            description TEXT,
            reservation_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT DEFAULT 'Menunggu', 
            rejection_reason TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 3. Tabel Log IoT (Sensor Masuk/Keluar)
    c.execute('''
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL, 
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Buat Akun Operator Default jika belum ada
    c.execute('SELECT * FROM users WHERE username = ?', ('operator',))
    if c.fetchone() is None:
        print("Membuat akun default: operator / admin123")
        c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                  ('operator', 'operator@mail.id', 'admin123', 'admin'))
    conn.commit()
    conn.close()


# --- HELPER: HITUNG STATUS BERDASARKAN WAKTU ---
def calculate_status(date_str, start_str, end_str):
    now = datetime.now()
    try:
        # Gabungkan tanggal dan jam menjadi format waktu lengkap
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


# --- HELPER: UPDATE STATUS MASAL ---
def update_all_reservation_statuses():
    conn = get_db_connection()
    # PENTING: Hanya update jadwal yang SUDAH DISETUJUI.
    # Jangan sentuh yang statusnya masih 'Menunggu' atau 'Ditolak'.
    reservations = conn.execute("SELECT * FROM reservations WHERE status NOT IN ('Menunggu', 'Ditolak')").fetchall()

    for res in reservations:
        new_status = calculate_status(res['reservation_date'], res['start_time'], res['end_time'])
        # Jika status perhitungan beda dengan di database, update!
        if res['status'] != new_status:
            conn.execute('UPDATE reservations SET status = ? WHERE id = ?', (new_status, res['id']))

    conn.commit()
    conn.close()


# =========================================
#                 ROUTES
# =========================================

@app.route('/')
def index():
    return redirect(url_for('dashboard'))


# --- LOGIN & LOGOUT ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()

        if user:
            # JIKA SUKSES
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            # JIKA GAGAL (Username/Password Salah)
            flash('Username atau Password salah!', 'danger')
            return redirect(url_for('dashboard'))

    # Jika user mencoba akses /login lewat URL langsung, lempar ke dashboard saja
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Berhasil logout.', 'info')
    return redirect(url_for('dashboard'))


# --- DASHBOARD (Statistik IoT & Status User) ---
@app.route('/dashboard')
def dashboard():
    # 1. Update status jadwal dulu biar real-time
    update_all_reservation_statuses()

    conn = get_db_connection()
    today_str = date.today().strftime('%Y-%m-%d')

    # 2. Hitung Statistik IoT (Pengunjung)
    masuk_today = conn.execute("SELECT COUNT(*) FROM visitor_logs WHERE direction='in' AND date(timestamp) = ?",
                               (today_str,)).fetchone()[0]
    keluar_today = conn.execute("SELECT COUNT(*) FROM visitor_logs WHERE direction='out' AND date(timestamp) = ?",
                                (today_str,)).fetchone()[0]
    total_today = masuk_today + keluar_today

    # 3. Ambil Reservasi Saya (Untuk User melihat status Request-nya)
    my_reservations = []
    if session.get('loggedin'):
        user_id = session['id']
        # User melihat SEMUA status (Menunggu, Ditolak, Terjadwal, dll)
        my_reservations = conn.execute('SELECT * FROM reservations WHERE user_id = ? ORDER BY id DESC LIMIT 5',
                                       (user_id,)).fetchall()

    conn.close()

    return render_template('dashboard.html',
                           username=session.get('username'),
                           role=session.get('role'),
                           loggedin=session.get('loggedin'),
                           total_today=total_today,
                           masuk_today=masuk_today,
                           keluar_today=keluar_today,
                           my_reservations=my_reservations)


# --- SCHEDULE (Jadwal Publik) ---
@app.route('/schedule')
def schedule():
    update_all_reservation_statuses()
    conn = get_db_connection()

    # FILTER: Hanya tampilkan yang sudah DISETUJUI (Terjadwal/Aktif/Selesai)
    # Sembunyikan 'Menunggu' dan 'Ditolak' dari publik
    reservations = conn.execute(
        "SELECT * FROM reservations WHERE status NOT IN ('Menunggu', 'Ditolak') ORDER BY reservation_date DESC, start_time ASC").fetchall()

    conn.close()
    return render_template('schedule.html',
                           jadwal=reservations,
                           loggedin=session.get('loggedin'),
                           role=session.get('role'),
                           username=session.get('username'))


# --- RESERVASI (Form User) ---
@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    if not session.get('loggedin'):
        flash('Wajib login untuk reservasi', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        conn = get_db_connection()
        # INSERT DATA: Status otomatis 'Menunggu'
        conn.execute('''
            INSERT INTO reservations (user_id, pic_name, description, reservation_date, start_time, end_time, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session['id'], request.form['pic_name'], request.form['description'], request.form['date'],
              request.form['start_time'], request.form['end_time'], 'Menunggu'))

        conn.commit()
        conn.close()

        flash('Permintaan reservasi dikirim! Menunggu persetujuan Admin.', 'info')
        return redirect(url_for('dashboard'))

    return render_template('reservation.html',
                           loggedin=True,
                           role=session.get('role'),
                           username=session.get('username'))


# --- [BARU] HALAMAN INBOX ADMIN ---
@app.route('/manage_reservations')
def manage_reservations():
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    # Ambil semua data yang statusnya 'Menunggu'
    pending_list = conn.execute('''
        SELECT r.*, u.username as requester 
        FROM reservations r 
        JOIN users u ON r.user_id = u.id 
        WHERE r.status = 'Menunggu' 
        ORDER BY r.reservation_date ASC
    ''').fetchall()
    conn.close()

    return render_template('manage_reservations.html',
                           pending_list=pending_list,
                           loggedin=True,
                           role='admin',
                           username=session.get('username'))


# --- [BARU] AKSI ADMIN: SETUJUI ---
@app.route('/approve/<int:id>')
def approve(id):
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    res = conn.execute('SELECT * FROM reservations WHERE id = ?', (id,)).fetchone()

    if res:
        # Hitung status waktu (apakah langsung Aktif atau masih Terjadwal)
        initial_status = calculate_status(res['reservation_date'], res['start_time'], res['end_time'])

        # Update status jadi status waktu tersebut
        conn.execute('UPDATE reservations SET status = ? WHERE id = ?', (initial_status, id))
        conn.commit()
        flash('Reservasi berhasil disetujui.', 'success')

    conn.close()
    return redirect(url_for('manage_reservations'))


# --- [BARU] AKSI ADMIN: TOLAK ---
@app.route('/reject/<int:id>', methods=['POST'])
def reject(id):
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    # Ambil alasan dari form (popup JS tadi)
    reason = request.form.get('reason', 'Ditolak oleh Admin')

    conn = get_db_connection()
    # Update status jadi 'Ditolak' dan simpan alasannya
    conn.execute('UPDATE reservations SET status = ?, rejection_reason = ? WHERE id = ?', ('Ditolak', reason, id))
    conn.commit()
    conn.close()

    flash('Reservasi ditolak.', 'warning')
    return redirect(url_for('manage_reservations'))


# --- [BARU] AKSI ADMIN: HAPUS JADWAL ---
@app.route('/delete_schedule/<int:id>')
def delete_schedule(id):
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    conn.execute('DELETE FROM reservations WHERE id = ?', (id,))
    conn.commit()
    conn.close()

    flash('Jadwal berhasil dihapus permanen.', 'success')
    return redirect(url_for('schedule'))


# --- USER MANAGEMENT ---
@app.route('/user')
def user():
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()

    return render_template('user.html',
                           users=users,
                           total_user=len(users),
                           count_admin=0,
                           count_guru=0,
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

    return render_template('add_user.html',
                           loggedin=True,
                           role='admin',
                           username=session.get('username'))


@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    target_user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if target_user:
        if target_user['username'] == 'operator':
            flash('ERROR: Akun Super Admin tidak boleh dihapus!', 'danger')
        else:
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            flash(f"User {target_user['username']} berhasil dihapus.", 'success')

    conn.close()
    return redirect(url_for('user'))


# --- API SENSOR IOT ---
@app.route('/api/sensor', methods=['POST'])
def api_sensor():
    data = request.json
    direction = data.get('direction')

    if direction in ['in', 'out']:
        conn = get_db_connection()
        conn.execute('INSERT INTO visitor_logs (direction, timestamp) VALUES (?, ?)',
                     (direction, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"Data {direction} saved"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid direction"}), 400


# --- TEST HELPER (Untuk simulasi manual) ---
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


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)