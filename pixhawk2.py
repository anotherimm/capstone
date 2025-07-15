import time
import math
from datetime import datetime
from pymavlink import mavutil
import firebase_admin
from firebase_admin import credentials, db

# --- 1. INISIALISASI FIREBASE (TETAP SAMA) ---
cred = credentials.Certificate("dht22raspi-firebase-adminsdk-fbsvc-70a4eb8653.json") 
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://dht22raspi-default-rtdb.asia-southeast1.firebasedatabase.app/'
})
# ----------------------------------------------------------------

# --- 2. KONEKSI KE PIXHAWK ---
# GANTI INI! sesuaikan dengan koneksi Anda.
# Jika via USB: '/dev/ttyACM0' atau '/dev/ttyUSB0'
# Jika via GPIO UART: '/dev/serial0'
# Coba dulu dengan TCP, jika gagal, ganti dengan UDP dari Solusi 2.
connection_string = 'tcp:192.168.26.28:5762'
baud_rate = 115200

print(f"Menghubungkan ke SIMULATOR di {connection_string}...")
master = mavutil.mavlink_connection(connection_string, baud=baud_rate)
master.wait_heartbeat()
print("Heartbeat diterima! Koneksi berhasil.")

# --- 3. FUNGSI BARU UNTUK MEMERINTAHKAN PENGIRIMAN DATA ---
def force_request_data(master):
    """Fungsi untuk mengirim perintah set message interval."""
    # Minta ATTITUDE (ID 30) dikirim 2 kali per detik (frekuensi 2 Hz -> interval 500000 us)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
        30,  # ID Pesan (30 untuk ATTITUDE)
        500000, # Interval dalam mikrodetik (500,000 us = 0.5 detik = 2 Hz)
        0, 0, 0, 0, 0)

    # Minta GLOBAL_POSITION_INT (ID 33) dikirim 2 kali per detik
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
        33,  # ID Pesan (33 untuk GLOBAL_POSITION_INT)
        500000,
        0, 0, 0, 0, 0)
        
    # Minta SYS_STATUS (ID 1) dikirim 1 kali per detik (interval 1000000 us)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
        1,  # ID Pesan (1 untuk SYS_STATUS)
        1000000,
        0, 0, 0, 0, 0)
    print("Perintah MAV_CMD_SET_MESSAGE_INTERVAL telah dikirim.")

# Panggil fungsi baru ini
force_request_data(master)

# --- 4. LOOP UTAMA (TETAP SAMA) ---
telemetry_data = {}
last_send_time = time.time()
send_interval = 5

print(f"Mulai membaca data telemetri...")

while True:
    msg = master.recv_msg()
    if not msg:
        continue
    
    # Debugging: Cetak tipe pesan yang masuk untuk melihat apa saja yang diterima
    print(f"Msg In: {msg.get_type()}", end='\r')

    msg_type = msg.get_type()
    if msg_type == 'ATTITUDE':
        telemetry_data['roll'] = f"{math.degrees(msg.roll):.2f}"
        telemetry_data['pitch'] = f"{math.degrees(msg.pitch):.2f}"
    elif msg_type == 'GLOBAL_POSITION_INT':
        telemetry_data['lat'] = msg.lat / 1e7
        telemetry_data['lon'] = msg.lon / 1e7
    elif msg_type == 'SYS_STATUS':
        telemetry_data['volt_baterai'] = msg.voltage_battery / 1000.0
    
    current_time = time.time()
    if (current_time - last_send_time) > send_interval:
        if telemetry_data:
            now = datetime.now()
            date_key = now.strftime("%Y-%m-%d")
            time_key = now.strftime("%H:%M:%S")
            ref = db.reference('/pixhawk/telemetry')
            ref.child(date_key).child(time_key).set(telemetry_data)
            print(f"\n==> Data dikirim: {telemetry_data}")
            last_send_time = current_time
            telemetry_data = {}
        else:
            print("\nMenunggu data telemetri pertama terkumpul...")
