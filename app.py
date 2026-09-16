"""
Бэкенд «Золотая крышка» с поддержкой PostgreSQL (Railway) и JSON-файла (локально).

RAILWAY:
  1. Создай проект на railway.app
  2. Add Service → Database → PostgreSQL  (Railway даст DATABASE_URL автоматически)
  3. Add Service → GitHub Repo → выбери свой репозиторий
  4. В настройках сервиса: Start Command = gunicorn app:app
  5. Готово. Две ссылки:
       https://твой-домен.up.railway.app/       → соло
       https://твой-домен.up.railway.app/plus1  → +1

ЛОКАЛЬНО (без базы):
  pip install flask gunicorn
  python app.py
  Данные сохраняются в players.json рядом с этим файлом.
"""

from flask import Flask, request, jsonify, send_from_directory
import json, os, threading

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
lock = threading.Lock()

# ── выбираем хранилище ────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL')  # Railway ставит автоматически

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    # Railway иногда даёт URL вида postgres://, psycopg2 хочет postgresql://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    def get_conn():
        return psycopg2.connect(DATABASE_URL)

    def init_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS players (
                        gid TEXT PRIMARY KEY,
                        name TEXT NOT NULL DEFAULT 'Гость',
                        caps INTEGER NOT NULL DEFAULT 1000,
                        tg TEXT
                    )
                """)
            conn.commit()

    init_db()

    def db_get_all():
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT gid, name, caps, tg FROM players ORDER BY caps DESC LIMIT 50")
                return [dict(r) for r in cur.fetchall()]

    def db_get_one(gid):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT gid, name, caps, tg FROM players WHERE gid=%s", (gid,))
                row = cur.fetchone()
                return dict(row) if row else None

    def db_upsert(gid, name, caps, tg_new):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Вставляем или обновляем — телеграм не трогаем если tg_new пустой
                cur.execute("""
                    INSERT INTO players (gid, name, caps, tg)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (gid) DO UPDATE SET
                        name = EXCLUDED.name,
                        caps = EXCLUDED.caps,
                        tg   = CASE
                                 WHEN %s = '-'     THEN NULL
                                 WHEN %s != ''     THEN %s
                                 ELSE players.tg       -- пустое → оставляем старое
                               END
                """, (gid, name, caps, tg_new or None,
                      tg_new or '', tg_new or '', tg_new or None))
            conn.commit()

    USE_PG = True

else:
    # ── JSON-файл (локальная разработка) ─────────────────────────
    DATA_FILE = os.path.join(BASE_DIR, 'players.json')
    USE_PG = False

    def _load():
        if not os.path.exists(DATA_FILE):
            return {}
        try:
            with open(DATA_FILE, encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(data):
        tmp = DATA_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

    def db_get_all():
        with lock:
            data = _load()
        return sorted(data.values(), key=lambda p: p.get('caps', 0), reverse=True)[:50]

    def db_get_one(gid):
        with lock:
            return _load().get(gid)

    def db_upsert(gid, name, caps, tg_new):
        with lock:
            data = _load()
            existing = data.get(gid, {})
            existing.update({'gid': gid, 'name': name, 'caps': caps})
            if tg_new == '-':
                existing.pop('tg', None)
            elif tg_new:
                existing['tg'] = tg_new
            data[gid] = existing
            _save(data)

# ── валидация ─────────────────────────────────────────────────────
MAX_GID  = 64
MAX_NAME = 40
MAX_TG   = 40
MAX_CAPS = 10_000_000

def clean(v, n):
    return str(v or '').strip()[:n]

# ── маршруты ─────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'invite-solo.html')

@app.route('/plus1')
def plus1():
    return send_from_directory(BASE_DIR, 'invite-plus1.html')

@app.route('/anthem.mp3')
def anthem():
    return send_from_directory(BASE_DIR, 'anthem.mp3')

@app.route('/api/players', methods=['GET'])
def get_players():
    return jsonify(db_get_all())

@app.route('/api/players/<path:gid>', methods=['GET'])
def get_player(gid):
    row = db_get_one(clean(gid, MAX_GID).lower())
    return (jsonify(row), 200) if row else (jsonify({}), 404)

@app.route('/api/players', methods=['POST'])
def post_player():
    body = request.get_json(force=True, silent=True) or {}
    gid  = clean(body.get('gid'),  MAX_GID).lower()
    if not gid:
        return jsonify({'ok': False, 'error': 'missing gid'}), 400

    name = clean(body.get('name'), MAX_NAME) or 'Гость'
    try:
        caps = max(0, min(int(body.get('caps', 0)), MAX_CAPS))
    except (TypeError, ValueError):
        caps = 0
    tg = clean(body.get('tg'), MAX_TG)

    db_upsert(gid, name, caps, tg)
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(debug=False, port=5000)
