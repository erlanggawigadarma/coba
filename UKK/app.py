from flask import Flask, render_template, redirect, url_for, session, flash, request, jsonify
import sqlite3
from datetime import datetime, date, timedelta

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
            role TEXT NOT NULL DEFAULT 'user'
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

            # Untuk AJAX request, kirim response JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'redirect': url_for('dashboard')
                })
            else:
                flash('Login berhasil!', 'success')
                return redirect(url_for('dashboard'))
        else:
            # JIKA GAGAL
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Username atau password salah!'
                }), 401
            else:
                flash('Username atau Password salah!', 'danger')
                return redirect(url_for('dashboard'))

    # Jika user mencoba akses /login lewat URL langsung, lempar ke dashboard saja
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Berhasil logout.', 'info')
    return redirect(url_for('dashboard'))


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

    # 3. AMBIL JADWAL HARI INI UNTUK SEMUA USER (TIDAK TERGANTUNG LOGIN)
    #    Tampilkan semua jadwal yang sudah disetujui (Aktif, Terjadwal, Selesai)
    todays_schedule = conn.execute('''
        SELECT * FROM reservations 
        WHERE reservation_date = ? 
        AND status IN ('Aktif', 'Terjadwal', 'Selesai')
        ORDER BY start_time ASC
    ''', (today_str,)).fetchall()

    conn.close()

    return render_template('dashboard.html',
                           username=session.get('username'),
                           role=session.get('role'),
                           loggedin=session.get('loggedin'),
                           total_today=total_today,
                           masuk_today=masuk_today,
                           keluar_today=keluar_today,
                           todays_schedule=todays_schedule)  # HANYA todays_schedule, TIDAK ADA my_reservations


# --- HALAMAN RESERVASI SAYA (FULL LIST) ---
@app.route('/my_reservations')
def my_reservations():
    if not session.get('loggedin'):
        flash('Silahkan login terlebih dahulu.', 'warning')
        return redirect(url_for('dashboard'))

    user_id = session['id']  # AMBIL ID USER YANG SEDANG LOGIN
    username = session['username']  # AMBIL USERNAME YANG SEDANG LOGIN

    conn = get_db_connection()

    # Mengambil SEMUA reservasi milik user yang sedang login (BERDASARKAN USER_ID)
    my_full_list = conn.execute('''
        SELECT * FROM reservations 
        WHERE user_id = ? 
        ORDER BY reservation_date DESC, start_time DESC
    ''', (user_id,)).fetchall()

    conn.close()

    return render_template('my_reservations.html',
                           my_full_list=my_full_list,
                           loggedin=True,
                           role=session.get('role'),
                           now_date=date.today().strftime('%Y-%m-%d'),
                           username=username)  # Kirim username ke template

# --- SCHEDULE (Jadwal Publik) ---
@app.route('/schedule')
def schedule():
    update_all_reservation_statuses() # Memperbarui status jadwal secara real-time
    conn = get_db_connection()
    today_str = date.today().strftime('%Y-%m-%d') # Mendapatkan tanggal hari ini

    # Cek apakah pengguna adalah admin (operator)
    if session.get('loggedin') and session.get('role') == 'admin':
        # Admin dapat melihat SEMUA riwayat jadwal (termasuk yang sudah lewat)
        query = """
            SELECT * FROM reservations 
            WHERE status NOT IN ('Menunggu', 'Ditolak') 
            ORDER BY reservation_date DESC, start_time ASC
        """
        reservations = conn.execute(query).fetchall()
    else:
        # User/Tamu hanya melihat jadwal hari ini dan seterusnya
        query = """
            SELECT * FROM reservations 
            WHERE status NOT IN ('Menunggu', 'Ditolak') 
            AND reservation_date >= ? 
            ORDER BY reservation_date ASC, start_time ASC
        """
        reservations = conn.execute(query, (today_str,)).fetchall()

    conn.close()
    return render_template('schedule.html',
                           jadwal=reservations,
                           loggedin=session.get('loggedin'),
                           role=session.get('role'),
                           now_date=date.today().strftime('%Y-%m-%d'),
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
                           count_user=0,
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


# Tambahkan route ini di dalam file app.py Anda (sebelum blok if __name__ == '__main__':)

# --- API UNTUK DASHBOARD (AUTO-REFRESH & FILTER HARI INI SAJA) ---
@app.route('/api/stats')
def get_stats():
    conn = get_db_connection()
    # Menggunakan date('now', 'localtime') agar otomatis reset ke 0 saat ganti hari
    masuk = conn.execute(
        "SELECT COUNT(*) FROM visitor_logs WHERE direction='in' AND date(timestamp) = date('now', 'localtime')"
    ).fetchone()[0]

    keluar = conn.execute(
        "SELECT COUNT(*) FROM visitor_logs WHERE direction='out' AND date(timestamp) = date('now', 'localtime')"
    ).fetchone()[0]

    conn.close()

    return jsonify({
        "masuk": masuk,
        "keluar": keluar,
        "total": masuk - keluar
    })

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


# --- API UNTUK DATA HISTORIS PENGUNJUNG (7 hari terakhir) ---
@app.route('/api/historical_stats')
def get_historical_stats():
    conn = get_db_connection()

    # Ambil data 7 hari terakhir
    historical_data = []
    labels = []

    for i in range(6, -1, -1):  # Dari 6 hari lalu sampai hari ini
        date_obj = date.today() - timedelta(days=i)
        date_str = date_obj.strftime('%Y-%m-%d')

        # Nama hari dalam Bahasa Indonesia
        day_names = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
        day_index = date_obj.weekday()  # 0=Senin, 1=Selasa, ..., 6=Minggu
        day_name = day_names[day_index]

        masuk = conn.execute(
            "SELECT COUNT(*) FROM visitor_logs WHERE direction='in' AND date(timestamp) = ?",
            (date_str,)
        ).fetchone()[0]

        keluar = conn.execute(
            "SELECT COUNT(*) FROM visitor_logs WHERE direction='out' AND date(timestamp) = ?",
            (date_str,)
        ).fetchone()[0]

        total = masuk + keluar

        historical_data.append({
            'date': date_str,
            'day': day_name,
            'day_index': day_index,
            'masuk': masuk,
            'keluar': keluar,
            'total': total
        })

        # Format label: Sen 26/12
        labels.append(f"{day_name}\n{date_str[8:10]}/{date_str[5:7]}")

    conn.close()

    return jsonify({
        'labels': labels,
        'data': historical_data
    })


# --- ROUTE UNTUK CETAK LAPORAN (LANGSUNG KE HALAMAN CETAK) ---
@app.route('/print_report')
def print_report():
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    report_type = request.args.get('type', 'visitor')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Validasi tanggal
    if not start_date or not end_date:
        flash('Pilih periode laporan terlebih dahulu!', 'warning')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()

    if report_type == 'visitor':
        # Ambil data pengunjung
        daily_data = []
        summary = {'masuk': 0, 'keluar': 0, 'total': 0}

        current = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            day_name = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'][current.weekday()]

            masuk = conn.execute(
                "SELECT COUNT(*) FROM visitor_logs WHERE direction='in' AND date(timestamp) = ?",
                (date_str,)).fetchone()[0]
            keluar = conn.execute(
                "SELECT COUNT(*) FROM visitor_logs WHERE direction='out' AND date(timestamp) = ?",
                (date_str,)).fetchone()[0]
            total = masuk + keluar

            # Tetap tampilkan meskipun 0 agar laporan lengkap
            daily_data.append({
                'date': date_str,
                'day': day_name,
                'masuk': masuk,
                'keluar': keluar,
                'total': total
            })

            summary['masuk'] += masuk
            summary['keluar'] += keluar
            summary['total'] += total

            current += timedelta(days=1)

        conn.close()

        return render_template('print_report.html',
                               report_type='Pengunjung',
                               start_date=start_date,
                               end_date=end_date,
                               daily_data=daily_data,
                               summary=summary,
                               username=session.get('username'),
                               now=datetime.now)

    else:  # report_type == 'reservation'
        # Ambil data reservasi
        reservation_data = conn.execute('''
            SELECT r.*, u.username as requester
            FROM reservations r
            JOIN users u ON r.user_id = u.id
            WHERE date(r.reservation_date) >= ? AND date(r.reservation_date) <= ?
            AND r.status NOT IN ('Menunggu', 'Ditolak')
            ORDER BY r.reservation_date ASC, r.start_time ASC
        ''', (start_date, end_date)).fetchall()

        summary = {
            'total': len(reservation_data),
            'terjadwal': 0,
            'aktif': 0,
            'selesai': 0
        }

        formatted_data = []
        for res in reservation_data:
            # Hitung summary
            if res['status'] == 'Terjadwal':
                summary['terjadwal'] += 1
            elif res['status'] == 'Aktif':
                summary['aktif'] += 1
            elif res['status'] == 'Selesai':
                summary['selesai'] += 1

            # Format untuk template
            formatted_data.append({
                'date': res['reservation_date'],
                'start_time': res['start_time'],
                'end_time': res['end_time'],
                'description': res['description'],
                'pic_name': res['pic_name'],
                'status': res['status'],
                'requester': res['requester']
            })

        conn.close()

        return render_template('print_report.html',
                               report_type='Reservasi',
                               start_date=start_date,
                               end_date=end_date,
                               reservation_data=formatted_data,
                               summary=summary,
                               username=session.get('username'),
                               now=datetime.now)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)