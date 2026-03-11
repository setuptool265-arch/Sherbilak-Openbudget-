# 🗳️ OpenBudget.uz Ovoz Berish Telegram Boti

Telegram bot orqali **openbudget.uz** saytida loyihaga ovoz berish.

---

## ⚡ Tez ishga tushirish

### 1. Talab: Python 3.10+

```bash
python3 --version
```

### 2. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

### 3. Bot tokenini o'rnatish

```bash
# .env fayl yaratish
cp .env.example .env
```

`.env` faylini oching va `BOT_TOKEN` ni to'ldiring:
```
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Token olish: [@BotFather](https://t.me/BotFather) → `/newbot`

**Yoki** `bot.py` faylida to'g'ridan-to'g'ri:
```python
BOT_TOKEN = "7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 4. Ishga tushirish

```bash
python3 bot.py
```

---

## 📱 Bot ishlash tartibi

```
/start
  └─► Loyiha haqida ma'lumot + telefon so'raladi
        └─► Telefon raqam kiritiladi
              └─► Captcha rasmi yuboriladi
                    └─► Captcha javobi kiritiladi
                          └─► SMS kod yuboriladi
                                └─► SMS kodi kiritiladi
                                      └─► ✅ Ovoz qabul qilindi
                                          ❌ Xatolik sababi ko'rsatiladi
```

---

## 🖥️ Server (Linux) da background ishlatish

### Screen bilan:
```bash
screen -S ovozbot
python3 bot.py
# Ctrl+A, keyin D — detach (bot ishlashda qoladi)

# Qayta ulash:
screen -r ovozbot
```

### Systemd service sifatida (tavsiya):

```bash
sudo nano /etc/systemd/system/ovozbot.service
```

Quyidagini yozing:
```ini
[Unit]
Description=OpenBudget Vote Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/openbudget_bot
EnvironmentFile=/home/ubuntu/openbudget_bot/.env
ExecStart=/usr/bin/python3 /home/ubuntu/openbudget_bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ovozbot
sudo systemctl start ovozbot
sudo systemctl status ovozbot
```

---

## 🔧 Sozlamalar (`bot.py` ichida)

| O'zgaruvchi | Izoh |
|-------------|------|
| `BOT_TOKEN` | Telegram bot tokeni |
| `INITIATIVE_ID` | Ovoz beriladigan loyiha ID si |
| `BOARD_ID` | Board ID |

---

## 📊 Texnik xususiyatlar

- **aiogram 3.x** — zamonaviy async Telegram framework
- **aiohttp** — async HTTP, bir vaqtda 200+ ulanish
- **FSM (Finite State Machine)** — har bir foydalanuvchi holati mustaqil
- **MemoryStorage** — tez, RAM da saqlash
- Barcha xatoliklar aniq xabar bilan ko'rsatiladi
- `bot.log` faylida yozib boriladi

---

## ⚠️ Muhim

Bu bot faqat **qonuniy ovoz berish** uchun.
Har bir fuqaro faqat **1 marta** o'z raqami bilan ovoz bera oladi.
