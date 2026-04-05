from flask import Flask, render_template, redirect, url_for, session, flash, request, jsonify
import sqlite3
from datetime import datetime, date, timedelta
import urllib.request
import urllib.parse
import threading
import time

app = Flask(__name__)
app.secret_key = 'rahasia'

DB_NAME = 'db_ukk.db'
MAX_KAPASITAS = 10

# ======================================================
# KONFIGURASI TELEGRAM BOT (UNTUK NOTIFIKASI DARURAT)
# ======================================================
TELEGRAM_BOT_TOKEN = '8544862664:AAHyrx5xykMcflV16BiQJvHN0gEQ3EEM6g8'
TELEGRAM_CHAT_ID = '7514843536'
DELAY_PESAN_DARURAT = 30  # Jeda pengiriman pesan berulang (dalam detik)

# ======================================================
# KONFIGURASI ALAMAT & LOKASI GEDUNG (SHARELOC TELEGRAM)
# ======================================================
ALAMAT_LENGKAP = "Lab RPL SMKN 1 DLANGGU, Kec. Dlanggu, Kabupaten Mojokerto, Jawa Timur"
GEDUNG_LATITUDE = -7.551389
GEDUNG_LONGITUDE = 112.480417

# --- GLOBAL STATE UNTUK KONTROL ALARM IOT ---
system_state = {
    'emergency_active': False,
    'emergency_message': '',
    'esp32_ip': None,
    'evacuation_notified': False,
    'location_sent': False,
    'thread_running': False
}


# --- KONEKSI DATABASE ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# --- INISIALISASI DATABASE ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    ''')

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

    c.execute('''
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL, 
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('SELECT * FROM users WHERE username = ?', ('operator',))
    if c.fetchone() is None:
        c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                  ('operator', 'operator@mail.id', 'admin123', 'admin'))

    conn.commit()
    conn.close()


# --- HELPER: HITUNG STATUS BERDASARKAN WAKTU ---
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


# --- HELPER: UPDATE STATUS MASAL ---
def update_all_reservation_statuses():
    conn = get_db_connection()
    reservations = conn.execute("SELECT * FROM reservations WHERE status NOT IN ('Menunggu', 'Ditolak')").fetchall()

    for res in reservations:
        new_status = calculate_status(res['reservation_date'], res['start_time'], res['end_time'])
        if res['status'] != new_status:
            conn.execute('UPDATE reservations SET status = ? WHERE id = ?', (new_status, res['id']))

    conn.commit()
    conn.close()


# --- FUNGSI KIRIM TELEGRAM TEKS ---
def send_telegram_message(pesan_teks):
    """Fungsi mengirim pesan teks ke Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'text': pesan_teks,
            'parse_mode': 'Markdown'
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f">>> Gagal kirim pesan Telegram: {e}")


# --- FUNGSI KIRIM TELEGRAM SHARELOC (MAPS) ---
def send_telegram_location(lat, lon):
    """Fungsi mengirim Pin Lokasi (ShareLoc) ke Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendLocation"
        data = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'latitude': lat,
            'longitude': lon
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f">>> Gagal kirim lokasi Telegram: {e}")


# --- FUNGSI BACKGROUND: LOOPING DARURAT CERDAS ---
def emergency_monitor_thread():
    """Berjalan di background untuk cek kondisi & kirim pesan berulang"""
    system_state['thread_running'] = True
    print(">>> Thread Darurat Dimulai!")

    while system_state['emergency_active']:

        # Cek jumlah orang di dalam ruangan secara kronologis
        conn = get_db_connection()
        logs = conn.execute(
            "SELECT direction FROM visitor_logs WHERE date(timestamp) = date('now', 'localtime') ORDER BY timestamp ASC").fetchall()
        conn.close()

        total_dalam = 0
        for log in logs:
            if log['direction'] == 'in':
                total_dalam += 1
            else:
                total_dalam -= 1
                if total_dalam < 0:
                    total_dalam = 0

        # 1. JIKA MASIH ADA ORANG DI DALAM
        if total_dalam > 0:
            pesan = (
                "🚨 *LAPORAN DARURAT: KEBAKARAN GEDUNG* 🚨\n\n"
                "Sistem Sensor IoT mendeteksi adanya *TITIK API AKTIF* di dalam ruangan.\n\n"
                "🏢 *DETAIL LOKASI:*\n"
                f"📍 Alamat: _{ALAMAT_LENGKAP}_\n"
                f"📌 Titik Kordinat Maps terlampir di bawah.\n\n"
                "⚠️ *STATUS NYAWA (KRITIS):*\n"
                f"Sistem penghitung mendeteksi masih ada *{total_dalam} JIWA* yang terjebak di dalam area kebakaran.\n\n"
                "MOHON SEGERA KIRIMKAN UNIT PEMADAM KEBAKARAN DAN TIM EVAKUASI KE LOKASI SEKARANG JUGA!"
            )

            send_telegram_message(pesan)
            print(f">>> Telegram: Peringatan {total_dalam} jiwa dikirim.")

            if not system_state['location_sent']:
                send_telegram_location(GEDUNG_LATITUDE, GEDUNG_LONGITUDE)
                system_state['location_sent'] = True

            system_state['evacuation_notified'] = False

            # LOOPING JEDA PINTAR: TIDUR TAPI TETAP WASPADA TIAP DETIK
            for _ in range(DELAY_PESAN_DARURAT):
                if not system_state['emergency_active']:
                    break

                # Cek kilat ke database: Apakah detik ini orangnya sudah 0?
                conn = get_db_connection()
                cek_logs = conn.execute(
                    "SELECT direction FROM visitor_logs WHERE date(timestamp) = date('now', 'localtime')").fetchall()
                conn.close()
                cek_total = 0
                for log in cek_logs:
                    if log['direction'] == 'in':
                        cek_total += 1
                    else:
                        cek_total -= 1
                        if cek_total < 0: cek_total = 0

                # JIKA ORANG SUDAH 0, POTONG KOMPAS! LANGSUNG KELUAR DARI WAKTU TUNGGU!
                if cek_total == 0:
                    break

                time.sleep(1)

        # 2. JIKA ORANG SUDAH 0, TAPI ALARM MASIH BUNYI (API MASIH ADA)
        else:
            if not system_state['evacuation_notified']:
                pesan = (
                    "📢 *UPDATE STATUS: EVAKUASI SELESAI*\n\n"
                    "Berdasarkan pantauan sensor pintu otomatis, saat ini *SUDAH TIDAK ADA ORANG (0 Jiwa)* di dalam ruangan.\n"
                    "Seluruh pengunjung telah berhasil keluar gedung.\n\n"
                    "🔥 *PERINGATAN:* Sirine alarm masih menyala dan titik api *MASIH AKTIF/BELUM PADAM*. "
                    "Fokuskan tindakan pada pemadaman aset gedung!"
                )

                send_telegram_message(pesan)

                if not system_state['location_sent']:
                    send_telegram_location(GEDUNG_LATITUDE, GEDUNG_LONGITUDE)
                    system_state['location_sent'] = True

                print(">>> Telegram: Pesan evakuasi 0 Jiwa dikirim.")
                system_state['evacuation_notified'] = True

            time.sleep(2)  # Cek setiap 2 detik apakah alarm dimatikan

    # ========================================================
    # KELUAR DARI WHILE LOOP (KARENA ALARM DIMATIKAN VIA WEB)
    # ========================================================
    pesan_aman = (
        "✅ *STATUS DARURAT DICABUT (AMAN)*\n\n"
        "Sistem kendali pusat telah mematikan sirine alarm kebakaran.\n"
        "Api dipastikan telah padam dan situasi gedung sudah kembali kondusif.\n\n"
        "Terima kasih atas respons cepatnya."
    )
    send_telegram_message(pesan_aman)
    print(">>> Telegram: Pesan KONDISI AMAN dikirim. Thread selesai.")
    system_state['thread_running'] = False


# =========================================
#                 ROUTES WEB
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
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'redirect': url_for('dashboard')
                })
            else:
                flash('Login berhasil!', 'success')
                return redirect(url_for('dashboard'))
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Username atau password salah!'
                }), 401
            else:
                flash('Username atau Password salah!', 'danger')
                return redirect(url_for('dashboard'))

    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Berhasil logout.', 'info')
    return redirect(url_for('dashboard'))


# --- DASHBOARD ---
@app.route('/dashboard')
def dashboard():
    update_all_reservation_statuses()

    conn = get_db_connection()
    today_str = date.today().strftime('%Y-%m-%d')

    # LOGIKA KRONOLOGIS UNTUK DASHBOARD
    logs = conn.execute("SELECT direction FROM visitor_logs WHERE date(timestamp) = ? ORDER BY timestamp ASC",
                        (today_str,)).fetchall()

    masuk_today = 0
    keluar_today = 0
    total_today = 0

    for log in logs:
        if log['direction'] == 'in':
            masuk_today += 1
            total_today += 1
        else:
            keluar_today += 1
            total_today -= 1
            if total_today < 0:
                total_today = 0

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
                           max_kapasitas=MAX_KAPASITAS,
                           todays_schedule=todays_schedule)


# --- HALAMAN RESERVASI SAYA (FULL LIST) ---
@app.route('/my_reservations')
def my_reservations():
    if not session.get('loggedin'):
        flash('Silahkan login terlebih dahulu.', 'warning')
        return redirect(url_for('dashboard'))

    user_id = session['id']
    username = session['username']

    conn = get_db_connection()
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
                           username=username)


# --- SCHEDULE (Jadwal Publik) ---
@app.route('/schedule')
def schedule():
    update_all_reservation_statuses()
    conn = get_db_connection()
    today_str = date.today().strftime('%Y-%m-%d')

    if session.get('loggedin') and session.get('role') == 'admin':
        query = """
            SELECT * FROM reservations 
            WHERE status NOT IN ('Menunggu', 'Ditolak') 
            ORDER BY reservation_date DESC, start_time ASC
        """
        reservations = conn.execute(query).fetchall()
    else:
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


# --- HALAMAN INBOX ADMIN ---
@app.route('/manage_reservations')
def manage_reservations():
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
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


# --- AKSI ADMIN: SETUJUI ---
@app.route('/approve/<int:id>')
def approve(id):
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    res = conn.execute('SELECT * FROM reservations WHERE id = ?', (id,)).fetchone()

    if res:
        initial_status = calculate_status(res['reservation_date'], res['start_time'], res['end_time'])
        conn.execute('UPDATE reservations SET status = ? WHERE id = ?', (initial_status, id))
        conn.commit()
        flash('Reservasi berhasil disetujui.', 'success')

    conn.close()
    return redirect(url_for('manage_reservations'))


# --- AKSI ADMIN: TOLAK ---
@app.route('/reject/<int:id>', methods=['POST'])
def reject(id):
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    reason = request.form.get('reason', 'Ditolak oleh Admin')

    conn = get_db_connection()
    conn.execute('UPDATE reservations SET status = ?, rejection_reason = ? WHERE id = ?', ('Ditolak', reason, id))
    conn.commit()
    conn.close()

    flash('Reservasi ditolak.', 'warning')
    return redirect(url_for('manage_reservations'))


# --- AKSI ADMIN: HAPUS JADWAL ---
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

    count_admin = len([u for u in users if u['role'] == 'admin'])
    count_guru = len([u for u in users if u['role'] == 'user'])

    return render_template('user.html',
                           users=users,
                           total_user=len(users),
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


# =========================================
#             API IOT KONTROL
# =========================================
@app.route('/api/sensor', methods=['POST'])
def api_sensor():
    # SIMPAN IP ESP32 SECARA OTOMATIS
    system_state['esp32_ip'] = request.remote_addr

    data = request.json

    # 1. Deteksi Darurat Kebakaran
    if data and 'emergency' in data:
        if not system_state['emergency_active']:
            system_state['emergency_active'] = True
            system_state['emergency_message'] = data['emergency']

            # Reset penanda ShareLoc dan Evakuasi untuk event kebakaran baru ini
            system_state['location_sent'] = False
            system_state['evacuation_notified'] = False

            # Start background thread jika belum jalan
            if not system_state['thread_running']:
                bg_thread = threading.Thread(target=emergency_monitor_thread)
                bg_thread.daemon = True
                bg_thread.start()

        return jsonify({"status": "emergency_logged"}), 200

    # 2. Deteksi Pengunjung Normal (Masuk / Keluar)
    direction = data.get('direction')
    if direction in ['in', 'out']:
        conn = get_db_connection()
        conn.execute('INSERT INTO visitor_logs (direction, timestamp) VALUES (?, ?)',
                     (direction, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

        # HITUNG KRONOLOGIS UNTUK ESP32
        logs = conn.execute(
            "SELECT direction FROM visitor_logs WHERE date(timestamp) = date('now', 'localtime') ORDER BY timestamp ASC").fetchall()
        conn.close()

        total_dalam = 0
        is_anomaly = False  # Variabel untuk melacak anomali

        for log in logs:
            if log['direction'] == 'in':
                total_dalam += 1
                is_anomaly = False  # Anomali hilang jika ada yang masuk
            else:
                total_dalam -= 1
                if total_dalam < 0:
                    total_dalam = 0
                    is_anomaly = True  # Anomali muncul jika minus (keluar saat kosong)

        # Cek apakah kapasitas ruangan sudah mencapai batas maksimal
        is_full = total_dalam >= MAX_KAPASITAS

        # Kirim balasan lengkap ke ESP32 agar ESP32 tahu harus membunyikan alarm apa
        return jsonify({
            "status": "success",
            "message": f"Data {direction} saved",
            "is_full": is_full,
            "is_anomaly": is_anomaly
        }), 200

    return jsonify({"status": "error", "message": "Invalid direction"}), 400

@app.route('/api/stats')
def get_stats():
    conn = get_db_connection()
    logs = conn.execute(
        "SELECT direction FROM visitor_logs WHERE date(timestamp) = date('now', 'localtime') ORDER BY timestamp ASC").fetchall()
    conn.close()

    masuk = 0
    keluar = 0
    total_dalam = 0
    is_anomaly = False
    anomaly_count = 0

    for log in logs:
        if log['direction'] == 'in':
            masuk += 1
            total_dalam += 1
            # Begitu masuk, anomali lenyap!
            is_anomaly = False
        else:
            keluar += 1
            total_dalam -= 1
            if total_dalam < 0:
                total_dalam = 0
                # Anomali muncul jika minus (artinya sensor ngaco di detik ini)
                is_anomaly = True
                anomaly_count += 1

    return jsonify({
        "masuk": masuk,
        "keluar": keluar,
        "total": total_dalam,
        "is_anomaly": is_anomaly,
        "anomaly_level": anomaly_count,
        "is_full": total_dalam >= MAX_KAPASITAS,
        "emergency": system_state['emergency_active'],
        "emergency_message": system_state['emergency_message']
    })


# --- API BARU: Untuk Mematikan Alarm dari Web ke Alat ESP32 ---
@app.route('/api/stop_alarm', methods=['POST'])
def api_stop_alarm():
    # HANYA USER YANG LOGIN YANG BISA MEMATIKAN ALARM
    if not session.get('loggedin'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    # Mematikan ini akan membuat while loop di thread otomatis berhenti (break)
    system_state['emergency_active'] = False

    # Tembak sinyal balik (HTTP GET) ke ESP32 berdasarkan IP yang sudah tersimpan
    if system_state['esp32_ip']:
        try:
            url = f"http://{system_state['esp32_ip']}/stop_alarm"
            urllib.request.urlopen(url, timeout=2)
        except Exception as e:
            print(f"Peringatan: Gagal mengirim sinyal mematikan buzzer ke ESP32 ({e})")

    return jsonify({"success": True, "message": "Alarm dimatikan. Laporan AMAN dikirim."})


@app.route('/api/historical_stats')
def get_historical_stats():
    conn = get_db_connection()

    historical_data = []
    labels = []

    for i in range(6, -1, -1):
        date_obj = date.today() - timedelta(days=i)
        date_str = date_obj.strftime('%Y-%m-%d')

        day_names = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
        day_index = date_obj.weekday()
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

        labels.append(f"{day_name}\n{date_str[8:10]}/{date_str[5:7]}")

    conn.close()

    return jsonify({
        'labels': labels,
        'data': historical_data
    })


@app.route('/print_report')
def print_report():
    if not session.get('loggedin') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    report_type = request.args.get('type', 'visitor')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        flash('Pilih periode laporan terlebih dahulu!', 'warning')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()

    if report_type == 'visitor':
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

    else:
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
            if res['status'] == 'Terjadwal':
                summary['terjadwal'] += 1
            elif res['status'] == 'Aktif':
                summary['aktif'] += 1
            elif res['status'] == 'Selesai':
                summary['selesai'] += 1

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