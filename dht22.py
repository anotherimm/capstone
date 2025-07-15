import time
import board
import adafruit_dht
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
# --- INISIALISASI FIREBASE ---
# GANTI DENGAN NAMA FILE KUNCI JSON ANDA
cred = credentials.Certificate("dht22raspi-firebase-adminsdk-fbsvc-70a4eb8653.json") 

# GANTI DENGAN URL DATABASE ANDA
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://dht22raspi-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# Menentukan path di database tempat data akan disimpan
ref = db.reference('/sensor/dht22')
# ----------------------------


# --- INISIALISASI SENSOR DHT22 ---
dht_pin = board.D24
try:
    dhtDevice = adafruit_dht.DHT22(dht_pin)
except RuntimeError as error:
    print(f"Gagal menginisialisasi sensor: {error.args[0]}")
    exit()
# -------------------------------

print("Memulai skrip: Membaca data sensor dan mengirim ke Firebase...")
print("Struktur data: /sensor/dht22/YYYY-MM-DD/HH:MM:SS")
print("Tekan Ctrl+C untuk berhenti.")

# --- 3. LOOP UTAMA ---
while True:
    try:
        # Baca suhu dan kelembapan dari sensor.
        temperature_c = dhtDevice.temperature
        humidity = dhtDevice.humidity

        # Pastikan pembacaan sensor berhasil sebelum mengirim.
        if temperature_c is not None and humidity is not None:
            print(f"Suhu: {temperature_c:.1f}°C | Kelembapan: {humidity:.1f}%")

            # Buat objek waktu saat ini.
            now = datetime.now()
            # Pisahkan menjadi kunci tanggal dan kunci waktu.
            date_key = now.strftime("%Y-%m-%d")
            time_key = now.strftime("%H:%M:%S")
            
            # Siapkan data yang akan dikirim.
            data = {
                'suhu': f"{temperature_c:.1f}",
                'kelembapan': f"{humidity:.1f}"
            }

            # Tentukan referensi utama di database.
            ref = db.reference('/sensor/dht22')
            
            # Kirim data menggunakan path bertingkat: /tanggal/waktu.
            ref.child(date_key).child(time_key).set(data)
            
            print(f"==> Data berhasil dikirim ke path /{date_key}/{time_key}")

    except RuntimeError as error:
        # Error pembacaan sering terjadi pada DHT, ini normal. Cukup lewati.
        print(f"Gagal membaca data dari sensor: {error.args[0]}")
    except Exception as e:
        # Menangani error lain yang mungkin terjadi (misal: koneksi internet putus).
        print(f"Terjadi error: {e}")

    # Beri jeda 10 detik sebelum pembacaan dan pengiriman berikutnya.
    # Anda bisa mengubah jeda ini sesuai kebutuhan.
    time.sleep(10)