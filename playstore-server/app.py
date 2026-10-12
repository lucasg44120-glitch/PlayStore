"""Play Store maison : serveur Flask (API + hébergement des fichiers d'installation)."""
import hmac, json, shutil, sqlite3, time, uuid, secrets
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory, session
from werkzeug.utils import secure_filename

import config

BASE = Path(__file__).parent.resolve()
DATA = BASE / "data"
UPLOADS = DATA / "uploads"          # icônes + captures (publics)
INSTALLERS = DATA / "installers"    # .exe etc. (servis uniquement via /download/<id>)
UPLOADS.mkdir(parents=True, exist_ok=True)
INSTALLERS.mkdir(parents=True, exist_ok=True)

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
BIN_EXT = {".exe", ".msi", ".msix", ".zip", ".7z", ".rar", ".apk", ".dmg", ".pkg", ".deb", ".rpm", ".appimage", ".jar"}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = (config.MAX_UPLOAD_MB + 10) * 1024 * 1024
key_file = DATA / "secret.key"
if not key_file.exists():
    key_file.write_text(secrets.token_hex(32))
app.secret_key = key_file.read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=12 * 3600)


# ---------- base de données ----------
def q(sql, args=(), one=False, commit=False):
    c = sqlite3.connect(DATA / "store.db")
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, args)
        if commit:
            c.commit()
            return None
        return cur.fetchone() if one else cur.fetchall()
    finally:
        c.close()


q("""CREATE TABLE IF NOT EXISTS apps(
    id TEXT PRIMARY KEY, name TEXT, dev TEXT, cat TEXT, version TEXT, descr TEXT, url TEXT,
    icon TEXT, shots TEXT DEFAULT '[]', fname TEXT, fpath TEXT, bytes INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0, at REAL)""", commit=True)


def human(n):
    if not n:
        return ""
    return f"{n / 1e6:.1f} Mo" if n >= 1e6 else f"{max(1, round(n / 1e3))} Ko"


def pub(r):
    return {"id": r["id"], "name": r["name"], "dev": r["dev"], "cat": r["cat"], "version": r["version"],
            "desc": r["descr"], "url": r["url"], "icon": "/uploads/" + r["icon"] if r["icon"] else "",
            "shots": ["/uploads/" + s for s in json.loads(r["shots"] or "[]")],
            "fname": r["fname"], "bytes": r["bytes"], "size": human(r["bytes"]),
            "downloads": r["downloads"], "at": r["at"]}


# ---------- sécurité ----------
def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            return jsonify(error="Non autorisé"), 401
        return f(*a, **k)
    return w


@app.before_request
def csrf():
    if request.method in ("POST", "PUT", "DELETE") and request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify(error="Requête refusée"), 403


@app.after_request
def headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r


@app.errorhandler(413)
def too_big(_):
    return jsonify(error=f"Fichier trop gros (max {config.MAX_UPLOAD_MB} Mo)"), 413


fails = {}


@app.post("/api/login")
def login():
    ip = request.remote_addr
    n, t = fails.get(ip, (0, 0))
    if n >= 5 and time.time() - t < 60:
        return jsonify(error="Trop d'essais, réessaie dans 1 minute"), 429
    d = request.get_json(silent=True) or {}
    ok = hmac.compare_digest(str(d.get("user", "")).encode(), config.ADMIN_USER.encode()) & \
         hmac.compare_digest(str(d.get("password", "")).encode(), config.ADMIN_PASSWORD.encode())
    if not ok:
        fails[ip] = (n + 1, time.time())
        return jsonify(error="Identifiants incorrects"), 401
    fails.pop(ip, None)
    session.permanent = True
    session["admin"] = True
    return jsonify(admin=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(admin=False)


@app.get("/api/me")
def me():
    return jsonify(admin=bool(session.get("admin")))


# ---------- fichiers ----------
def save_image(fs):
    if not fs or not fs.filename:
        return None
    ext = Path(fs.filename).suffix.lower()
    if ext not in IMG_EXT:
        raise ValueError("Image invalide (png, jpg, webp, gif)")
    name = uuid.uuid4().hex + ext
    fs.save(UPLOADS / name)
    return name


def save_installer(fs, aid):
    if not fs or not fs.filename:
        return None
    ext = Path(fs.filename).suffix.lower()
    if ext not in BIN_EXT:
        raise ValueError("Type de fichier non autorisé (" + ", ".join(sorted(BIN_EXT)) + ")")
    fname = secure_filename(fs.filename) or "installeur" + ext
    if not fname.lower().endswith(ext):
        fname += ext
    d = INSTALLERS / aid
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    fs.save(d / fname)
    return fname, f"{aid}/{fname}", (d / fname).stat().st_size


def rm_upload(name):
    if name:
        (UPLOADS / name).unlink(missing_ok=True)


def fields():
    f = request.form
    url = f.get("url", "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise ValueError("Lien invalide (http:// ou https://)")
    name = f.get("name", "").strip()
    if not name:
        raise ValueError("Nom requis")
    return dict(name=name[:80], dev=f.get("dev", "")[:80], cat=f.get("cat", "Outils")[:30],
                version=f.get("version", "1.0")[:20], descr=f.get("desc", "")[:5000], url=url)


# ---------- API ----------
@app.get("/api/apps")
def list_apps():
    return jsonify([pub(r) for r in q("SELECT * FROM apps ORDER BY at DESC")])


@app.post("/api/apps")
@admin_required
def create():
    try:
        v = fields()
        aid = uuid.uuid4().hex[:10]
        icon = save_image(request.files.get("icon"))
        shots = [save_image(s) for s in request.files.getlist("shots")[:4] if s and s.filename]
        inst = save_installer(request.files.get("installer"), aid)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    fname, fpath, size = inst or ("", "", 0)
    q("INSERT INTO apps(id,name,dev,cat,version,descr,url,icon,shots,fname,fpath,bytes,at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (aid, v["name"], v["dev"], v["cat"], v["version"], v["descr"], v["url"], icon or "", json.dumps(shots),
       fname, fpath, size, time.time()), commit=True)
    return jsonify(pub(q("SELECT * FROM apps WHERE id=?", (aid,), one=True))), 201


@app.put("/api/apps/<aid>")
@admin_required
def update(aid):
    r = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
    if not r:
        abort(404)
    try:
        v = fields()
        icon = save_image(request.files.get("icon"))
        new = [s for s in request.files.getlist("shots")[:4] if s and s.filename]
        shots = [save_image(s) for s in new]
        inst = save_installer(request.files.get("installer"), aid)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if icon:
        rm_upload(r["icon"])
    if new:
        for s in json.loads(r["shots"] or "[]"):
            rm_upload(s)
    fname, fpath, size = inst or (r["fname"], r["fpath"], r["bytes"])
    q("UPDATE apps SET name=?,dev=?,cat=?,version=?,descr=?,url=?,icon=?,shots=?,fname=?,fpath=?,bytes=? WHERE id=?",
      (v["name"], v["dev"], v["cat"], v["version"], v["descr"], v["url"], icon or r["icon"],
       json.dumps(shots) if new else r["shots"], fname, fpath, size, aid), commit=True)
    return jsonify(pub(q("SELECT * FROM apps WHERE id=?", (aid,), one=True)))


@app.delete("/api/apps/<aid>")
@admin_required
def delete(aid):
    r = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
    if not r:
        abort(404)
    rm_upload(r["icon"])
    for s in json.loads(r["shots"] or "[]"):
        rm_upload(s)
    shutil.rmtree(INSTALLERS / aid, ignore_errors=True)
    q("DELETE FROM apps WHERE id=?", (aid,), commit=True)
    return jsonify(ok=True)


@app.get("/download/<aid>")
def download(aid):
    r = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
    if not r or not r["fpath"]:
        abort(404)
    q("UPDATE apps SET downloads=downloads+1 WHERE id=?", (aid,), commit=True)
    return send_file(INSTALLERS / r["fpath"], as_attachment=True, download_name=r["fname"], conditional=True)


@app.get("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(UPLOADS, name)


@app.get("/")
def index():
    return send_from_directory(BASE / "static", "index.html")


if __name__ == "__main__":
    if config.ADMIN_PASSWORD == "admin123":
        print("⚠️  Change ADMIN_PASSWORD dans config.py avant de publier le serveur !")
    print(f"▶ Play Store : http://localhost:{config.PORT}")
    try:
        from waitress import serve
        serve(app, host=config.HOST, port=config.PORT, threads=8,
              max_request_body_size=app.config["MAX_CONTENT_LENGTH"], channel_timeout=900)
    except ImportError:
        app.run(host=config.HOST, port=config.PORT)
