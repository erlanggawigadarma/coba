from machine import Pin
import network
import socket
import time
import json
import urequests

# ===== KONFIGURASI WiFi =====
WIFI_SSID = "Redmi 10C"      # Ganti dengan nama WiFi Anda
WIFI_PASSWORD = "20070718"      # Ganti dengan password WiFi Anda

# ===== KONFIGURASI FLASK SERVER =====
FLASK_SERVER = "http://10.132.179.227:5000/"  # Pastikan IP komputer Anda benar
API_ENDPOINT = f"{FLASK_SERVER}/api/sensor"

# ===== KONFIGURASI PIN SENSOR & AKTUATOR =====
# 1. Sensor Ultrasonik 1 (Luar/Entry)
TRIG_PIN_1 = 5
ECHO_PIN_1 = 18
trigger1 = Pin(TRIG_PIN_1, Pin.OUT)
echo1 = Pin(ECHO_PIN_1, Pin.IN, Pin.PULL_DOWN)

# 2. Sensor Ultrasonik 2 (Dalam/Exit)
TRIG_PIN_2 = 19
ECHO_PIN_2 = 21
trigger2 = Pin(TRIG_PIN_2, Pin.OUT)
echo2 = Pin(ECHO_PIN_2, Pin.IN, Pin.PULL_DOWN)

# 3. Buzzer (Alarm)
BUZZER_PIN = 13
buzzer = Pin(BUZZER_PIN, Pin.OUT)
buzzer.value(0)  # Pastikan mati saat awal nyala

# 4. Sensor Api (Flame Sensor)
FLAME_PIN = 4
flame_sensor = Pin(FLAME_PIN, Pin.IN, Pin.PULL_UP)

# ===== PENGATURAN SISTEM =====
CALIBRATION_FACTOR = 58.0
DETECTION_THRESHOLD = 100  # cm 
DETECTION_TIMEOUT = 4000   # ms 
MIN_DISTANCE_CHANGE = 30   # cm 
DEBOUNCE_TIME = 400        # ms 

# Counter data lokal 
counter_data = {
    "masuk": 0,
    "keluar": 0,
    "total": 0
}

# State untuk deteksi
state = {
    "sensor1_triggered": False,
    "sensor2_triggered": False,
    "trigger_time": 0,
    "baseline_dist1": 0,
    "baseline_dist2": 0,
    "calibrated": False,
    "last_event_time": 0,
    "both_clear": True
}

# STATUS ALARM GLOBAL
fire_alarm_active = False
last_buzzer_toggle = 0  
buzzer_state = 0        

# ==========================================
# FUNGSI-FUNGSI ALARM & NOTIFIKASI
# ==========================================
def alarm_penuh():
    """Buzzer bunyi Tiiiiiiiiiiit (1 detik penuh) untuk penuh"""
    if fire_alarm_active: return 
    
    print("⚠️ DARI WEB: Ruangan Penuh!")
    buzzer.value(1)
    time.sleep_ms(1000) # Bunyi 1 detik penuh (Sangat berbeda dengan penuh)
    buzzer.value(0)

def alarm_anomali():
    """Buzzer bunyi Tit.. Tit.. Tit.."""
    if fire_alarm_active: return 
    
    print("⚠️ DARI WEB: Anomali Terdeteksi!")
    for _ in range(3):
        buzzer.value(1)
        time.sleep_ms(80)   # Nyala sangat cepat (80ms)
        buzzer.value(0)
        time.sleep_ms(120)  # Jeda mati yang lebih jelas (120ms)
    

def send_emergency_to_flask():
    """Kirim sinyal darurat bencana ke Flask"""
    try:
        payload = json.dumps({"emergency": "Terdeteksi Titik Api / Kebakaran!"})
        headers = {"Content-Type": "application/json"}
        response = urequests.post(API_ENDPOINT, data=payload, headers=headers)
        if response.status_code == 200:
            print("✓ Sinyal DARURAT berhasil dikirim ke Web!")
        response.close()
    except Exception as e:
        print(f"✗ Gagal kirim sinyal darurat: {e}")

def send_to_flask(direction):
    """Kirim data ke Flask server dan tunggu perintah sirine"""
    try:
        payload = json.dumps({"direction": direction})
        headers = {"Content-Type": "application/json"}
        response = urequests.post(API_ENDPOINT, data=payload, headers=headers)
        
        if response.status_code == 200:
            print(f"✓ Data '{direction}' berhasil dikirim ke Flask")
            try:
                resp_data = response.json()
                
                # Cek balasan dari web, alarm mana yang harus dibunyikan?
                if resp_data.get("is_anomaly", False):
                    alarm_anomali()
                elif resp_data.get("is_full", False):
                    alarm_penuh()
                    
            except Exception as e:
                pass
        response.close()
    except Exception as e:
        print(f"✗ Gagal kirim ke Flask: {e}")

# ==========================================
# FUNGSI KONEKSI & SENSOR ULTRASONIK
# ==========================================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    time.sleep(1)
    
    print("Connecting to WiFi...")
    try:
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
        print()
        if wlan.isconnected():
            print("WiFi Connected! IP:", wlan.ifconfig()[0])
            return wlan.ifconfig()[0]
        return None
    except Exception as e:
        return None

def single_measure(trigger, echo):
    trigger.value(0)
    time.sleep_ms(2)
    trigger.value(1)
    time.sleep_us(10)
    trigger.value(0)
    
    count = 0
    while echo.value() == 0 and count < 5000: count += 1
    if count >= 5000: return None
    
    start = time.ticks_us()
    count = 0
    while echo.value() == 1 and count < 5000: count += 1
    if count >= 5000: return None
    
    end = time.ticks_us()
    return time.ticks_diff(end, start)

def measure_distance(trigger, echo):
    valid_readings = []
    for i in range(2):
        duration = single_measure(trigger, echo)
        if duration is not None:
            distance = duration / CALIBRATION_FACTOR
            if 1 <= distance <= 400:
                valid_readings.append(distance)
        time.sleep_ms(20)
    
    if len(valid_readings) >= 1:
        return sum(valid_readings) / len(valid_readings)
    return -1

def detect_direction(dist1, dist2):
    global state, counter_data
    
    if not state["calibrated"]:
        if dist1 > 0 and dist2 > 0:
            state["baseline_dist1"] = dist1
            state["baseline_dist2"] = dist2
            state["calibrated"] = True
            print(f"✓ Baseline: S1={dist1:.1f}cm, S2={dist2:.1f}cm")
        return
    
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, state["last_event_time"]) < DEBOUNCE_TIME: return
    
    change1 = abs(state["baseline_dist1"] - dist1) if dist1 > 0 and state["baseline_dist1"] > 0 else 0
    change2 = abs(state["baseline_dist2"] - dist2) if dist2 > 0 and state["baseline_dist2"] > 0 else 0
    
    sensor1_detected = dist1 > 0 and change1 > MIN_DISTANCE_CHANGE
    sensor2_detected = dist2 > 0 and change2 > MIN_DISTANCE_CHANGE
    both_clear = not sensor1_detected and not sensor2_detected
    
    if time.ticks_diff(current_time, state["trigger_time"]) > DETECTION_TIMEOUT or (both_clear and state["both_clear"]):
        state["sensor1_triggered"] = False
        state["sensor2_triggered"] = False
    
    state["both_clear"] = both_clear
    
    if sensor1_detected and not state["sensor1_triggered"] and not state["sensor2_triggered"]:
        state["sensor1_triggered"] = True
        state["trigger_time"] = current_time
    
    if state["sensor1_triggered"] and sensor2_detected and not state["sensor2_triggered"]:
        state["sensor2_triggered"] = True
        counter_data["masuk"] += 1
        counter_data["total"] = counter_data["masuk"] - counter_data["keluar"]
        state["last_event_time"] = current_time
        print(f"✅ MASUK! (Lokal: {counter_data['total']})")
        send_to_flask("in")
        state["sensor1_triggered"] = False
        state["sensor2_triggered"] = False
        return
    
    if sensor2_detected and not state["sensor2_triggered"] and not state["sensor1_triggered"]:
        state["sensor2_triggered"] = True
        state["trigger_time"] = current_time
    
    if state["sensor2_triggered"] and sensor1_detected and not state["sensor1_triggered"]:
        state["sensor1_triggered"] = True
        counter_data["keluar"] += 1
        counter_data["total"] = counter_data["masuk"] - counter_data["keluar"]
        state["last_event_time"] = current_time
        print(f"❌ KELUAR! (Lokal: {counter_data['total']})")
        send_to_flask("out")
        state["sensor1_triggered"] = False
        state["sensor2_triggered"] = False
        return

def start_server(ip):
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(5)
    return s

# ==========================================
# PROGRAM UTAMA (MAIN LOOP)
# ==========================================
ip = connect_wifi()
if ip is None:
    print("Cannot start without WiFi!")
    raise SystemExit

server = start_server(ip)

print("\n" + "=" * 50)
print("Sistem Keamanan & People Counter Aktif!")
print("=" * 50)
print("⚙️ Kalibrasi baseline dalam 3 detik... Jangan halangi sensor!")
time.sleep(3)

last_update = 0

while True:
    try:
        current_ms = time.ticks_ms()
        
        # 1. CEK SENSOR API (PRIORITAS UTAMA)
        if flame_sensor.value() == 0 and not fire_alarm_active:
            print("🔥 BAHAYA KEBAKARAN! Alarm aktif.")
            fire_alarm_active = True
            send_emergency_to_flask()
            
        # 2. BUNYIKAN ALARM DARURAT (BENAR-BENAR NON-BLOCKING)
        if fire_alarm_active:
            if time.ticks_diff(current_ms, last_buzzer_toggle) > 200:
                buzzer_state = 1 if buzzer_state == 0 else 0
                buzzer.value(buzzer_state)
                last_buzzer_toggle = current_ms
        else:
            buzzer.value(0) 
            
        # 3. CEK SENSOR ULTRASONIK 
        if time.ticks_diff(current_ms, last_update) > 50:
            dist1 = measure_distance(trigger1, echo1)
            time.sleep_ms(10) 
            dist2 = measure_distance(trigger2, echo2)
            
            detect_direction(dist1, dist2)
            last_update = time.ticks_ms()
        
        # 4. HANDLE LOKAL WEB SERVER REQUEST 
        server.settimeout(0.05) 
        try:
            conn, addr = server.accept()
            request = conn.recv(1024).decode()
            
            if '/stop_alarm' in request:
                fire_alarm_active = False 
                buzzer.value(0)           
                print("🔕 ALARM DIMATIKAN DARI WEB!")
                conn.send('HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nOK')
                
            conn.close()
        except OSError:
            pass
            
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.close()
        break
    except Exception as e:
        print(f"Error Loop: {e}")
        time.sleep(1)