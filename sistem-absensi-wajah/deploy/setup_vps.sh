#!/usr/bin/env bash
# =============================================================================
# Setup VPS Ubuntu untuk Sistem Absensi Wajah (IDCloudHost / VPS Ubuntu mana pun)
#
# Cara pakai (setelah proyek diunggah ke /opt/absensi):
#   cd /opt/absensi
#   bash deploy/setup_vps.sh              # otomatis pakai nama IP.sslip.io
#   bash deploy/setup_vps.sh DOMAIN.ANDA  # atau pakai domain sendiri
#
# Skrip ini akan:
#   1. memasang dependensi sistem (python3-venv, libgl untuk opencv, nginx)
#   2. membuat virtualenv + memasang dependensi Python (+ waitress)
#   3. mengunduh berkas model bila belum ada (models/)
#   4. memasang layanan systemd "absensi" (auto-start + auto-restart)
#   5. memasang konfigurasi nginx reverse proxy ke 127.0.0.1:5050
#
# Setelah selesai, lanjutkan dengan HTTPS (WAJIB agar kamera bisa diakses):
#   apt install -y certbot python3-certbot-nginx
#   certbot --nginx -d DOMAIN.ANDA
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${1:-}"
echo ">> Folder proyek: $APP_DIR"

echo ">> [1/5] Dependensi sistem..."
apt update
apt install -y python3-venv python3-pip nginx unzip curl
apt install -y libgl1 || true
apt install -y libglib2.0-0t64 2>/dev/null || apt install -y libglib2.0-0 || true

echo ">> [2/5] Virtualenv + dependensi Python..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo ">> [3/5] Berkas model..."
mkdir -p "$APP_DIR/models"
if [ ! -s "$APP_DIR/models/face_detection_yunet.onnx" ]; then
  curl -L -o "$APP_DIR/models/face_detection_yunet.onnx" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi
if [ ! -s "$APP_DIR/models/face_landmarker.task" ]; then
  curl -L -o "$APP_DIR/models/face_landmarker.task" \
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
fi
if [ ! -s "$APP_DIR/models/w600k_mbf.onnx" ]; then
  echo ">> Mengunduh ArcFace (buffalo_s) lalu mengekstrak w600k_mbf.onnx..."
  curl -L -o /tmp/buffalo_s.zip \
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip"
  unzip -o -j /tmp/buffalo_s.zip "w600k_mbf.onnx" -d "$APP_DIR/models/"
  rm -f /tmp/buffalo_s.zip
fi

echo ">> [4/5] Layanan systemd..."
cat > /etc/systemd/system/absensi.service <<EOF
[Unit]
Description=Sistem Absensi Wajah (Flask + waitress)
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/serve.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now absensi
sleep 2
systemctl --no-pager -l status absensi | head -12 || true

echo ">> [5/5] Nginx reverse proxy..."
IP_PUBLIK="$(curl -s ifconfig.me || echo IP-ANDA)"
if [ -z "$DOMAIN" ]; then
  DOMAIN="${IP_PUBLIK//./-}.sslip.io"
fi
sed "s/server_name _;/server_name ${DOMAIN};/" \
  "$APP_DIR/deploy/nginx-absensi.conf" > /etc/nginx/sites-available/absensi
ln -sf /etc/nginx/sites-available/absensi /etc/nginx/sites-enabled/absensi
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
echo ">> Nama alamat (server_name): $DOMAIN"

echo ""
echo "================================ SELESAI ================================"
echo " Aplikasi berjalan sebagai layanan 'absensi' di 127.0.0.1:5050 (waitress)"
echo " Nginx menampung port 80. Uji:    http://$IP_PUBLIK/"
echo ""
echo " LANGKAH TERAKHIR - HTTPS (WAJIB untuk akses kamera):"
echo "   apt install -y certbot python3-certbot-nginx"
echo "   certbot --nginx -d DOMAIN.ANDA"
echo ""
echo " Tanpa domain? Pakai nama gratis berbasis IP (sslip.io):"
echo "   certbot --nginx -d ${IP_PUBLIK//./-}.sslip.io"
echo "   lalu buka: https://${IP_PUBLIK//./-}.sslip.io/"
echo ""
echo " Pastikan port 80 dan 443 terbuka di firewall IDCloudHost (portal)."
echo " Perintah layanan: systemctl restart|stop|status absensi"
echo " Log aplikasi  : journalctl -u absensi -f"
echo "========================================================================="
