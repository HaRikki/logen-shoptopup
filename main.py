import os, time, hmac, hashlib, sqlite3, secrets, shutil, uuid, json, threading, urllib.request, urllib.parse
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
envf = BASE / ".env"
if envf.exists():
    for l in envf.read_text().splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
DATA = Path(os.getenv("DATA_DIR", BASE / "data")); UP = DATA / "uploads"; UP.mkdir(parents=True, exist_ok=True)
ADMIN_PATH = os.getenv("ADMIN_PATH", "admin123").strip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@logen.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
kf = DATA / "secret.key"
if not kf.exists(): kf.write_text(secrets.token_hex(32))
SECRET = (os.getenv("SECRET_KEY") or kf.read_text()).encode()

def db():
    c = sqlite3.connect(DATA / "logen.db"); c.row_factory = sqlite3.Row; return c
def q(sql, a=()):
    with db() as c: return [dict(r) for r in c.execute(sql, a).fetchall()]
def ex(sql, a=()):
    with db() as c: return c.execute(sql, a).lastrowid

ex("CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT)")
ex("CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, icon TEXT, image TEXT DEFAULT '', zone INTEGER DEFAULT 0, sort INTEGER DEFAULT 0)")
ex("CREATE TABLE IF NOT EXISTS packs(id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER, name TEXT, price REAL, sort INTEGER DEFAULT 0)")
ex("CREATE TABLE IF NOT EXISTS media(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, path TEXT)")
ex("CREATE TABLE IF NOT EXISTS orders(no TEXT PRIMARY KEY, game TEXT, player TEXT, pack TEXT, amount REAL, status TEXT, created INTEGER)")
DEF = {"site_name": "Logen TopUp", "logo": "", "khqr": "", "merchant": "Logen TopUp", "telegram": "", "notice": "ប្រាក់ចូលលឿន ២៤/៧ ⚡"}
for k, v in DEF.items(): ex("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
if not q("SELECT 1 FROM games"):
    for n, i, z, ps in [("Free Fire", "🔥", 0, [("100 Diamonds", 1), ("310 Diamonds", 3), ("520 Diamonds", 5), ("Weekly Pass", 2)]),
        ("Mobile Legends", "⚔️", 1, [("86 Diamonds", 1.5), ("172 Diamonds", 3), ("257 Diamonds", 4.5)]),
        ("Roblox Robux", "🧱", 0, [("80 Robux", 1), ("400 Robux", 5), ("800 Robux", 10)]),
        ("PUBG Mobile", "🎯", 0, [("60 UC", 1), ("325 UC", 5), ("660 UC", 10)])]:
        gid = ex("INSERT INTO games(name,icon,zone) VALUES(?,?,?)", (n, i, z))
        for j, (pn, pp) in enumerate(ps): ex("INSERT INTO packs(game_id,name,price,sort) VALUES(?,?,?,?)", (gid, pn, pp, j))

def settings(): return {r["k"]: r["v"] for r in q("SELECT * FROM settings")}
def games():
    gs = q("SELECT * FROM games ORDER BY sort,id")
    for g in gs: g["packs"] = q("SELECT id,name,price FROM packs WHERE game_id=? ORDER BY sort,id", (g["id"],))
    return gs

def sign(exp): return f"{exp}.{hmac.new(SECRET, str(exp).encode(), hashlib.sha256).hexdigest()}"
def auth(authorization: str = Header("")):
    try:
        exp, sig = authorization.replace("Bearer ", "").split(".")
        ok = hmac.compare_digest(sig, hmac.new(SECRET, exp.encode(), hashlib.sha256).hexdigest()) and int(exp) > time.time()
    except Exception: ok = False
    if not ok: raise HTTPException(401, "Unauthorized")
tries = {}
def notify(text):
    t, c = os.getenv("BOT_TOKEN"), os.getenv("CHAT_ID")
    if not (t and c): return
    def run():
        try: urllib.request.urlopen(f"https://api.telegram.org/bot{t}/sendMessage", urllib.parse.urlencode({"chat_id": c, "text": text}).encode(), timeout=10)
        except Exception: pass
    threading.Thread(target=run, daemon=True).start()

app = FastAPI(title="Logen TopUp", docs_url=None, redoc_url=None)

@app.get("/api/public")
def public():
    s = settings(); return {"settings": s, "games": games(), "media": q("SELECT * FROM media ORDER BY id")}

@app.post("/api/check-id")
def check_id(d: dict):
    gid, pid, zone = d.get("game_id"), str(d.get("player", "")).strip(), str(d.get("zone", "")).strip()
    g = q("SELECT * FROM games WHERE id=?", (gid,))
    if not g or not pid.isdigit() or not 5 <= len(pid) <= 14: raise HTTPException(400, "Invalid ID")
    if g[0]["zone"] and not zone.isdigit(): raise HTTPException(400, "Invalid Zone")
    # TODO: ភ្ជាប់ API ពិតសម្រាប់ទាញឈ្មោះ Player នៅទីនេះ (Provider របស់អ្នក)
    return {"ok": True, "player": pid, "zone": zone, "nickname": None}

@app.post("/api/orders")
def new_order(d: dict):
    g = q("SELECT * FROM games WHERE id=?", (d.get("game_id"),)); p = q("SELECT * FROM packs WHERE id=?", (d.get("pack_id"),))
    pid, zone = str(d.get("player", "")).strip(), str(d.get("zone", "")).strip()
    if not g or not p or p[0]["game_id"] != g[0]["id"] or not pid.isdigit(): raise HTTPException(400, "Bad order")
    no = "LG" + str(int(time.time()))[-6:] + secrets.token_hex(2).upper()
    player = pid + (f" ({zone})" if g[0]["zone"] else "")
    ex("INSERT INTO orders VALUES(?,?,?,?,?,?,?)", (no, g[0]["name"], player, p[0]["name"], p[0]["price"], "pending", int(time.time())))
    return q("SELECT * FROM orders WHERE no=?", (no,))[0]

@app.get("/api/orders/{no}")
def get_order(no: str):
    r = q("SELECT * FROM orders WHERE no=?", (no,))
    if not r: raise HTTPException(404, "Not found")
    return r[0]

@app.post("/api/orders/{no}/paid")
def claim(no: str):
    o = get_order(no)
    if o["status"] == "pending":
        ex("UPDATE orders SET status='waiting' WHERE no=?", (no,))
        notify(f"💰 Order {no}\n{o['game']} | {o['player']}\n{o['pack']} | ${o['amount']:.2f}")
    return {"ok": True}

@app.post("/api/admin/login")
def login(d: dict, request: Request):
    ip = request.client.host if request.client else "x"; n, t0 = tries.get(ip, (0, time.time()))
    if n >= 8 and time.time() - t0 < 600: raise HTTPException(429, "Too many attempts")
    if hmac.compare_digest(str(d.get("email")), ADMIN_EMAIL) and hmac.compare_digest(str(d.get("password")), ADMIN_PASSWORD):
        tries.pop(ip, None); return {"token": sign(int(time.time()) + 43200)}
    tries[ip] = (n + 1, t0 if n else time.time()); raise HTTPException(401, "Email ឬ Password ខុស")

def A(path, method):
    return app.api_route(path, methods=[method])

@app.get("/api/admin/data")
def adata(authorization: str = Header("")):
    auth(authorization); o = q("SELECT * FROM orders ORDER BY created DESC LIMIT 300")
    paid = [x for x in o if x["status"] == "paid"]
    return {"settings": settings(), "games": games(), "media": q("SELECT * FROM media ORDER BY id"), "orders": o,
            "stats": {"orders": len(o), "paid": len(paid), "revenue": sum(x["amount"] for x in paid)}}

@app.post("/api/admin/games")
def gadd(d: dict, authorization: str = Header("")):
    auth(authorization); return {"id": ex("INSERT INTO games(name,icon,zone) VALUES(?,?,0)", (d.get("name", "New Game"), "🎮"))}

@app.put("/api/admin/games/{gid}")
def gput(gid: int, d: dict, authorization: str = Header("")):
    auth(authorization)
    ex("UPDATE games SET name=?,icon=?,image=?,zone=? WHERE id=?", (d["name"], d.get("icon", ""), d.get("image", ""), 1 if d.get("zone") else 0, gid))
    if "packs" in d:
        ex("DELETE FROM packs WHERE game_id=?", (gid,))
        for i, p in enumerate(d["packs"]): ex("INSERT INTO packs(game_id,name,price,sort) VALUES(?,?,?,?)", (gid, p["name"], float(p["price"]), i))
    return {"ok": True}

@app.delete("/api/admin/games/{gid}")
def gdel(gid: int, authorization: str = Header("")):
    auth(authorization); ex("DELETE FROM packs WHERE game_id=?", (gid,)); ex("DELETE FROM games WHERE id=?", (gid,)); return {"ok": True}

@app.post("/api/admin/upload")
def upload(file: UploadFile = File(...), authorization: str = Header("")):
    auth(authorization); ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm", ".mov"}: raise HTTPException(400, "File type not allowed")
    name = uuid.uuid4().hex + ext
    with open(UP / name, "wb") as f: shutil.copyfileobj(file.file, f)
    return {"url": "/uploads/" + name, "kind": "video" if ext in {".mp4", ".webm", ".mov"} else "image"}

@app.post("/api/admin/media")
def madd(d: dict, authorization: str = Header("")):
    auth(authorization); return {"id": ex("INSERT INTO media(kind,path) VALUES(?,?)", (d["kind"], d["path"]))}

@app.delete("/api/admin/media/{mid}")
def mdel(mid: int, authorization: str = Header("")):
    auth(authorization); ex("DELETE FROM media WHERE id=?", (mid,)); return {"ok": True}

@app.put("/api/admin/settings")
def sput(d: dict, authorization: str = Header("")):
    auth(authorization)
    for k in DEF:
        if k in d: ex("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(d[k])))
    return {"ok": True}

@app.put("/api/admin/orders/{no}")
def oput(no: str, d: dict, authorization: str = Header("")):
    auth(authorization)
    if d.get("status") not in {"pending", "waiting", "paid", "rejected"}: raise HTTPException(400, "bad status")
    ex("UPDATE orders SET status=? WHERE no=?", (d["status"], no)); return {"ok": True}

@app.delete("/api/admin/orders/{no}")
def odel(no: str, authorization: str = Header("")):
    auth(authorization); ex("DELETE FROM orders WHERE no=?", (no,)); return {"ok": True}

@app.get("/" + ADMIN_PATH)
@app.get("/" + ADMIN_PATH + "/")
def admin_page(): return FileResponse(BASE / "static/admin.html", headers={"Cache-Control": "no-store"})

app.mount("/uploads", StaticFiles(directory=UP), name="uploads")
app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), proxy_headers=True, forwarded_allow_ips="*")
