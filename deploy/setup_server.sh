#!/bin/bash
# Развёртывание «Оқу» на Ubuntu 24.04 (запускается от root).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "== 1. Пакеты"
apt-get update -q
apt-get install -y -q python3-venv nginx ufw >/dev/null

echo "== 2. Подкачка 512 МБ (памяти всего 1 ГБ)"
if [ ! -f /swapfile ]; then
  fallocate -l 512M /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null
  swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 3. Пользователь и папки"
id oqu >/dev/null 2>&1 || useradd --system --home-dir /opt/oqu --shell /usr/sbin/nologin oqu
mkdir -p /opt/oqu/instance
rm -rf /opt/oqu/site.new && mkdir -p /opt/oqu/site.new
tar -xzf /tmp/oqu.tar.gz -C /opt/oqu/site.new
rm -rf /opt/oqu/site.old; [ -d /opt/oqu/site ] && mv /opt/oqu/site /opt/oqu/site.old
mv /opt/oqu/site.new /opt/oqu/site
rm -rf /opt/oqu/site/Для_сдачи /opt/oqu/site/docs /opt/oqu/site/tests

echo "== 4. Виртуальное окружение и зависимости"
[ -d /opt/oqu/venv ] || python3 -m venv /opt/oqu/venv
grep -vE '^(pytest|ruff|python-docx)' /opt/oqu/site/requirements.txt > /tmp/oqu-req.txt
/opt/oqu/venv/bin/pip install -q --disable-pip-version-check -r /tmp/oqu-req.txt
chown -R oqu:oqu /opt/oqu

echo "== 5. Настройки (секретный ключ — только на сервере)"
if [ ! -f /etc/oqu.env ]; then
  umask 077
  cat > /etc/oqu.env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
OQU_INSTANCE=/opt/oqu/instance
OQU_PUBLIC=1
OQU_TRUST_PROXY=1
EOF
fi

echo "== 6. Демо-база (если пустая)"
cd /opt/oqu/site
sudo -u oqu env OQU_INSTANCE=/opt/oqu/instance /opt/oqu/venv/bin/python -m app.seed

echo "== 7. Служба systemd"
cat > /etc/systemd/system/oqu.service <<'EOF'
[Unit]
Description=Oqu digital library (FastAPI)
After=network.target

[Service]
User=oqu
Group=oqu
WorkingDirectory=/opt/oqu/site
EnvironmentFile=/etc/oqu.env
ExecStart=/opt/oqu/venv/bin/uvicorn app.web:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3
MemoryMax=400M
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now oqu >/dev/null 2>&1
systemctl restart oqu

echo "== 8. nginx"
cat > /etc/nginx/sites-available/oqu <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name 342995.fornex.cloud 130.17.21.59;
    client_max_body_size 45m;
    server_tokens off;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/oqu /etc/nginx/sites-enabled/oqu
rm -f /etc/nginx/sites-enabled/default
nginx -t -q && systemctl reload nginx

echo "== 9. Файрвол: SSH, HTTP, HTTPS, панель BeAdmin"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 8080/tcp >/dev/null
ufw --force enable >/dev/null

echo "== 10. Ежедневная резервная копия базы (хранить 7 дней)"
cat > /etc/cron.daily/oqu-backup <<'EOF'
#!/bin/sh
mkdir -p /opt/oqu/backups
sqlite3_db=/opt/oqu/instance/library.sqlite
[ -f "$sqlite3_db" ] && /opt/oqu/venv/bin/python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d)" "$sqlite3_db" "/opt/oqu/backups/library-$(date +%F).sqlite"
find /opt/oqu/backups -name 'library-*.sqlite' -mtime +7 -delete
EOF
chmod 755 /etc/cron.daily/oqu-backup

sleep 2
echo "== Проверка"
systemctl is-active oqu
curl -s http://127.0.0.1:8000/api/health; echo
curl -s -o /dev/null -w "nginx: %{http_code}\n" http://127.0.0.1/api/health
free -h | head -2
df -h / | tail -1
