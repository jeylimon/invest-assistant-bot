#!/bin/bash
set -e

echo "=== Установка invest-assistant-bot ==="

apt-get update -qq
apt-get install -y python3 python3-pip git

cd /opt
if [ -d "invest-assistant-bot" ]; then
    echo "Обновляю существующую копию..."
    cd invest-assistant-bot && git pull
else
    git clone https://github.com/jeylimon/invest-assistant-bot.git
    cd invest-assistant-bot
fi

pip3 install -r requirements.txt

if [ -z "$BOT_TOKEN" ]; then
    echo ""
    read -p "Введи BOT_TOKEN (из BotFather или Railway): " BOT_TOKEN
fi

echo "BOT_TOKEN=$BOT_TOKEN" > /opt/invest-assistant-bot/.env
chmod 600 /opt/invest-assistant-bot/.env

cat > /etc/systemd/system/invest-bot.service << 'EOF'
[Unit]
Description=Invest Assistant Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/invest-assistant-bot
EnvironmentFile=/opt/invest-assistant-bot/.env
ExecStart=/usr/bin/python3 /opt/invest-assistant-bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable invest-bot
systemctl start invest-bot

echo ""
echo "=== Готово! Бот запущен ==="
echo ""
echo "Статус:  systemctl status invest-bot"
echo "Логи:    journalctl -u invest-bot -f"
echo "Стоп:    systemctl stop invest-bot"
