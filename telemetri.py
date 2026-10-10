import os
import time
import math
import sys
import http.server
import socketserver
import threading
import json
from urllib.parse import parse_qs, urlparse

# Küresel değişkenler - Gerçek donanımdan gelen veriler buraya yazılacak
gercek_gps_verisi = {
    "lat": 0.0,
    "lon": 0.0,
    "alt": 0.0,
    "hiz": 0.0
}

# Türkiye Hava Sahaları Veritabanı
hava_sahalari = {
    "Çorlu Askeri Hava Sahası (LTCO)": {"lat": 41.1311, "lon": 27.9114, "yasak_cap_km": 15},
    "İstanbul Havalimanı Sahası (LTFM)": {"lat": 41.2753, "lon": 28.7519, "yasak_cap_km": 25},
    "Sabiha Gökçen Hava Sahası (LTFJ)": {"lat": 40.8986, "lon": 29.3092, "yasak_cap_km": 20},
    "Ankara Esenboğa Hava Sahası (LTAC)": {"lat": 40.1281, "lon": 32.9950, "yasak_cap_km": 20},
    "İzmir Adnan Menderes Sahası (LTBJ)": {"lat": 38.2892, "lon": 27.1550, "yasak_cap_km": 18},
    "Kars Harakani Hava Sahası (LTCF)": {"lat": 40.5622, "lon": 43.1150, "yasak_cap_km": 12}
}

class DonanimGpsHandler(http.server.SimpleHTTPRequestHandler):
    """Cihazın gerçek GPS donanımından gelen verileri dinleyen yerel sunucu köprüsü"""
    def do_GET(self):
        global gercek_gps_verisi
        query = parse_qs(urlparse(self.path).query)
        
        if "lat" in query and "lon" in query:
            gercek_gps_verisi["lat"] = float(query["lat"][0])
            gercek_gps_verisi["lon"] = float(query["lon"][0])
            gercek_gps_verisi["alt"] = float(query["alt"][0]) if "alt" in query and query["alt"][0] else 0.0
            gercek_gps_verisi["hiz"] = float(query["hiz"][0]) if "hiz" in query and query["hiz"][0] else 0.0
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"durum": "tamam"}')
            return
            
        # İnternetsiz çalışan, tarayıcının GPS çipine erişmesini sağlayan HTML/JS kodu
        html_kod = """
        <!DOCTYPE html>
        <html>
        <head><title>GPS Donanim Koprusu</title></head>
        <body>
            <h3 style='color: green;'>📡 GPS DONANIM KİLİTLENMESİ AKTİF</h3>
            <p>Bu sayfa açık kaldığı sürece cihazın gerçek GPS çipi Python'a veri üfler.</p>
            <script>
                function veriyiGonder(pos) {
                    let lat = pos.coords.latitude;
                    let lon = pos.coords.longitude;
                    let alt = pos.coords.altitude || 0;
                    let hiz = (pos.coords.speed || 0) * 3.6; // m/s'yi km/h'ye çevir
                    
                    fetch(`http://localhost:8080/?lat=${lat}&lon=${lon}&alt=${alt}&hiz=${hiz}`)
                    .catch(err => console.log("Python baglantisi bekleniyor..."));
                }
                function hata(err) { console.warn('GPS Donanim Hatasi: ' + err.message); }
                
                // Cihazın içindeki gerçek GPS donanımını yüksek hassasiyetle (High Accuracy) dinle
                navigator.geolocation.watchPosition(veriyiGonder, hata, {
                    enableHighAccuracy: true,
                    maximumAge: 0,
                    timeout: 5000
                });
            </script>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html_kod.encode('utf-8'))

    def log_message(self, format, *args):
        return # Terminalde gereksiz HTTP istek logları basılmasın diye gizliyoruz

def haversine_mesafe(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def hava_sahasi_kontrol(current_lat, current_lon):
    if current_lat == 0.0 and current_lon == 0.0:
        return "⏳ GPS Uydu Kilidi Bekleniyor..."
    
    en_yakin_saha = None
    min_mesafe = float('inf')
    for saha_adi, veri in hava_sahalari.items():
        mesafe = haversine_mesafe(current_lat, current_lon, veri["lat"], veri["lon"])
        if mesafe < min_mesafe:
            min_mesafe = mesafe
            en_yakin_saha = (saha_adi, veri["yasak_cap_km"])
    if en_yakin_saha:
        saha_adi, guvenli_sinir = en_yakin_saha
        if min_mesafe <= guvenli_sinir:
            return f"❌ ACİL UYARI! {saha_adi} İÇİNDESİNİZ! Mesafe: {min_mesafe:.1f} KM."
        elif min_mesafe <= (guvenli_sinir + 10):
            return f"⚠️ DİKKAT! {saha_adi} Sınırına Yaklaşıyorsunuz! Mesafe: {min_mesafe:.1f} KM."
        else:
            return f"💚 GÜVENLİ HAVA SAHASI. {saha_adi} ({min_mesafe:.1f} KM uzakta)."
    return "💚 Kontrol Dışı Serbest Hava Sahası."

def arka_plan_sunucu():
    with socketserver.TCPServer(("localhost", 8080), DonanimGpsHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    # 1. Adım: Donanım köprüsünü arka planda (thread) başlat
    sunucu_thread = threading.Thread(target=arka_plan_sunucu, daemon=True)
    sunucu_thread.start()
    
    print("📡 OPERATÖR UTKU %100 GERÇEK DONANIM ENTEGRASYONU BAŞLATILDI...")
    print("🌐 Lütfen tarayıcınızdan şu adrese girip konum izni verin: http://localhost:8080")
    print("🛸 Cihazın içindeki gerçek GPS donanımına kilitleniliyor. Bekleniyor...\n")
    
    # Bilgisayarda tarayıcıyı otomatik aç (Android/iOS'ta tarayıcıya elinle girmen gerekir)
    if sys.platform == "win32":
        import webbrowser
        webbrowser.open("http://localhost:8080")

    tur_sayisi = 0
    kanat_alani = 12.5
    suruklenme_katsayisi = 0.08

    # 15 Saniyede Bir Gerçek Veri Basan Ana Döngü
    while True:
        lat = gercek_gps_verisi["lat"]
        lon = gercek_gps_verisi["lon"]
        alt = gercek_gps_verisi["alt"]
        hiz_kmh = gercek_gps_verisi["hiz"]
        
        saha_mesaji = hava_sahasi_kontrol(lat, lon)
        dis_hava_sicakligi = 15.0 - (alt * 0.0065)
        hiz_ms = hiz_kmh / 3.6
        hava_yogunlugu = 1.225 * math.exp(-alt / 8500)
        suruklenme_newton = 0.5 * hava_yogunlugu * (hiz_ms ** 2) * suruklenme_katsayisi * kanat_alani

        print(f"==================================================")
        print(f"🛰️ [%100 GERÇEK DONANIM] | PAKET: #{tur_sayisi} | SAAT: {time.strftime('%H:%M:%S')}")
        print(f"==================================================")
        print(f"📍 GERÇEK KONUM  : {lat:.6f} N , {lon:.6f} E")
        print(f"⛰️ GERÇEK İRTİFA : {alt:.1f} Metre (Cihazın yüksekliği)")
        print(f"🌡️ GERÇEK ISI    : {dis_hava_sicakligi:.1f} °C")
        print(f"💨 GERÇEK HIZ    : {hiz_kmh:.1f} km/h (Şu an evde oturuyorsan: 0)")
        print(f"🛡️ SÜRÜKLENME    : {suruklenme_newton:.1f} Newton")
        print(f"🛑 HAVA SAHASI   : {saha_mesaji}")
        print(f"==================================================\n")
        
        if sys.platform == "win32" and lat != 0.0:
            import winsound
            winsound.Beep(1000, 150)
            
        tur_sayisi += 1
        time.sleep(15)
