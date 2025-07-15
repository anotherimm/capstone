import time
import board
import busio
import numpy as np
from scipy.interpolate import griddata
from adafruit_amg88xx import AMG88XX
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import matplotlib.cm as cm

# --- KONFIGURASI PENGIRIM ---
WEB_SERVER_URL = "https://thermal-vision-nextjs.vercel.app/api/upload"
INTERVAL_DETIK = 1
IMAGE_SIZE = (256, 256)

# --- PARAMETER ALGORITMA DETEKSI PRESISI (UNTUK DISESUAIKAN) ---
# TAHAP 1: Deteksi Absolut
ABSOLUTE_FIRE_THRESHOLD = 150.0

# TAHAP 2: Deteksi Klaster
CLUSTER_PIXEL_COUNT_MIN = 2  # Minimal 2 piksel harus panas untuk dianggap klaster.
CLUSTER_PIXEL_TEMP = 65.0    # Suhu minimal untuk piksel dalam klaster.
CLUSTER_DIFFERENTIAL_FACTOR = 1.5 # Titik terpanas harus 50% lebih panas dari rata-rata.

# TAHAP 3: Validasi Piksel Tunggal
SINGLE_PIXEL_TEMP = 75.0 # Suhu minimal untuk anomali piksel tunggal (lebih tinggi dari klaster).
NEIGHBOR_DELTA_TEMP = 20.0 # Piksel tetangga harus 20°C lebih panas dari latar belakang.

# --- INISIALISASI ---
i2c = busio.I2C(board.SCL, board.SDA)
amg = AMG88XX(i2c)
print("Sistem Deteksi Presisi (Altitude) aktif...")
points = [(ix % 8, ix // 8) for ix in range(64)]
grid_x, grid_y = np.mgrid[0:7:IMAGE_SIZE[0]*1j, 0:7:IMAGE_SIZE[1]*1j]
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    alert_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
except IOError:
    font = ImageFont.load_default()
    alert_font = font

def process_and_highlight_fire_precision(raw_pixels):
    pixels_np = np.array(raw_pixels).reshape((8, 8))
    max_temp = np.max(pixels_np)
    average_temp = np.mean(pixels_np)
    fire_detected = False
    fire_coords = []
    hot_spots_indices = np.argwhere(pixels_np >= CLUSTER_PIXEL_TEMP)

    # --- ALGORITMA DETEKSI MULTI-TAHAP ---
    # Tahap 1: Api Absolut
    if max_temp >= ABSOLUTE_FIRE_THRESHOLD:
        fire_detected = True
        hot_spots_indices = np.argwhere(pixels_np == max_temp)

    # Tahap 2: Klaster Api
    elif len(hot_spots_indices) >= CLUSTER_PIXEL_COUNT_MIN:
        if max_temp >= average_temp * CLUSTER_DIFFERENTIAL_FACTOR:
            fire_detected = True

    # Tahap 3: Validasi Piksel Tunggal
    elif len(hot_spots_indices) == 1 and pixels_np[hot_spots_indices[0][0], hot_spots_indices[0][1]] >= SINGLE_PIXEL_TEMP:
        # Hanya ada 1 piksel panas, mari kita validasi
        (r, c) = hot_spots_indices[0]
        # Hitung suhu latar belakang (piksel dingin)
        ambient_mask = pixels_np < 40.0 # Anggap di bawah 40C adalah latar belakang
        ambient_temp = np.mean(pixels_np[ambient_mask]) if np.any(ambient_mask) else average_temp
        
        # Cek tetangga
        hot_neighbors = 0
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    if pixels_np[nr, nc] > ambient_temp + NEIGHBOR_DELTA_TEMP:
                        hot_neighbors += 1
        
        # Jika minimal ada 2 tetangga yang hangat, ini api sungguhan
        if hot_neighbors >= 2:
            fire_detected = True
    
    # Jika api terdeteksi, dapatkan koordinat untuk bounding box
    if fire_detected and len(hot_spots_indices) > 0:
        min_y, min_x = hot_spots_indices.min(axis=0)
        max_y, max_x = hot_spots_indices.max(axis=0)
        fire_coords = [min_x, min_y, max_x, max_y]

    # --- PEMBUATAN GAMBAR ---
    min_temp = np.min(pixels_np)
    pixels_normalized = (pixels_np.flatten() - min_temp) / (max_temp - min_temp if max_temp > min_temp else 1)
    bicubic = griddata(points, pixels_normalized, (grid_x, grid_y), method='cubic')
    rgb_array = (cm.inferno(bicubic)[:,:,:3] * 255).astype(np.uint8)
    thermal_image = Image.fromarray(rgb_array, 'RGB')
    draw = ImageDraw.Draw(thermal_image)
    
    # --- PENANDAAN VISUAL ---
    if fire_detected:
        draw.text((10, 10), "!!! API TERDETEKSI !!!", font=alert_font, fill=(255, 0, 0))
        if fire_coords:
            scale_x, scale_y = IMAGE_SIZE[0] / 8, IMAGE_SIZE[1] / 8
            x1, y1 = fire_coords[0] * scale_x, fire_coords[1] * scale_y
            x2, y2 = (fire_coords[2] + 1) * scale_x, (fire_coords[3] + 1) * scale_y
            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
    else:
        draw.text((10, 10), f"Max: {max_temp:.2f}°C", font=font, fill=(255, 255, 255))
    
    return thermal_image, fire_detected

# --- LOOP UTAMA ---
try:
    while True:
        raw_pixels = [p for row in amg.pixels for p in row]
        enhanced_image, fire_status = process_and_highlight_fire_precision(raw_pixels)
        buffer = io.BytesIO()
        enhanced_image.save(buffer, format="JPEG")
        buffer.seek(0)
        
        try:
            files = {'file': ('thermal.jpg', buffer, 'image/jpeg')}
            response = requests.post(WEB_SERVER_URL, files=files, timeout=2)
            print(f"Gambar terkirim, status: {response.status_code} | Deteksi Api: {fire_status}")
        except requests.exceptions.RequestException as e:
            print(f"Gagal mengirim gambar: {e}")
            
        time.sleep(INTERVAL_DETIK)

except KeyboardInterrupt:
    print("Program dihentikan.")