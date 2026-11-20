# Logen TopUp (FastAPI + SQLite)

## Run
```
./start.sh          # ឬ: pip install -r requirements.txt && python main.py
```
បើកៈ http://localhost:8000 · Admin: http://localhost:8000/admin123
កែ `.env` (ADMIN_PATH, ADMIN_EMAIL, ADMIN_PASSWORD) មុនដាក់ Online ជានិច្ច។

## Add Domain / Host
- **VPS**: run `python main.py` (port 8000) + Caddy (`Caddyfile`) ឬ Nginx reverse_proxy → 127.0.0.1:8000. ចង្អុល DNS A record ទៅ IP VPS។
- **Docker**: `docker build -t logen . && docker run -d -p 8000:8000 -v logen-data:/app/data --env-file .env logen`
- **Cloudflare Tunnel / Panel Host (Apsara ។ល។)**: Start command `python main.py`, PORT តាម Host; Domain ណាក៏បាន (គ្មាន URL ចាក់ដេកក្នុងកូដ)។
- **Render/Railway**: Start `python main.py`, ភ្ជាប់ Disk/Volume ទៅ `DATA_DIR` ដើម្បីរក្សា Database + Upload។

## Data
`data/logen.db` (SQLite) និង `data/uploads/` — Backup ពីរនេះគឺគ្រប់គ្រាន់។

## ចំណុចត្រូវភ្ជាប់បន្ត
- Check ID ទាញឈ្មោះ Player: `check_id()` ក្នុង main.py (TODO)
- KHQR: ឥឡូវជា QR Static របស់ ABA Merchant (Admin Upload); Auto-confirm (Bakong/ABA PayWay) អាចបន្ថែម
- Telegram ជូនដំណឹង Order: ដាក់ BOT_TOKEN + CHAT_ID ក្នុង .env
