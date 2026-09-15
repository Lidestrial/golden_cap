# Опциональный бэкенд для сайта-приглашения "Золотая крышка".
#
# ЗАЧЕМ ЭТО НУЖНО:
# Сайт внутри Claude.ai использует встроенное хранилище (window.storage), которое
# работает только внутри чата. Если ты заливаешь invite-solo.html и invite-plus1.html
# как обычные файлы на свой хостинг — window.storage там не существует, и общая
# картотека (кто сколько крышек накопил, чьи телеграм оставлены) не будет сохраняться.
#
# Этот файл — маленький Flask-бэкенд с хранением в одном JSON-файле на диске.
# Сайт сам определяет, где он запущен: если window.storage есть — использует его,
# если нет — стучится сюда, на /api/players. В HTML ничего менять не нужно.
#
# ЗАПУСК:
#   pip install flask
#   python app.py
# Открой  http://127.0.0.1:5000/       — соло-версия
#         http://127.0.0.1:5000/plus1  — версия с +1
#
# Рядом с этим файлом должны лежать:
#   invite-solo.html, invite-plus1.html, anthem.mp3
#
# ЧТОБЫ ГОСТИ ЗАШЛИ С ТЕЛЕФОНОВ по локальной сети — запусти так:
#   app.run(host='0.0.0.0', port=5000)
# и дай им адрес вида http://ТВОЙ_IP:5000/

from flask import Flask, request, jsonify, send_from_directory
import json
import os
import threading

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'players.json')
lock = threading.Lock()

# Ограничения, чтобы никто не заспамил файл мусором
MAX_NAME_LEN = 40
MAX_TG_LEN = 40
MAX_GID_LEN = 64
MAX_CAPS = 10_000_000
MAX_PLAYERS = 500


def load_players():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_players(data):
    # Пишем во временный файл и подменяем — так JSON не побьётся,
    # если процесс упадёт в момент записи.
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def clean_str(value, max_len):
    if not isinstance(value, str):
        return ''
    return value.strip()[:max_len]


# ---------- страницы ----------

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'invite-solo.html')


@app.route('/plus1')
def plus1():
    return send_from_directory(BASE_DIR, 'invite-plus1.html')


@app.route('/anthem.mp3')
def anthem():
    return send_from_directory(BASE_DIR, 'anthem.mp3')


# ---------- общая картотека (крышки + телеграм) ----------

@app.route('/api/players', methods=['GET'])
def get_players():
    with lock:
        data = load_players()
    players = sorted(data.values(), key=lambda p: p.get('caps', 0), reverse=True)
    return jsonify(players[:50])


@app.route('/api/players/<gid>', methods=['GET'])
def get_player(gid):
    """Отдаёт запись одного гостя — сайт дёргает это при входе,
    чтобы перенести крышки и телеграм на новое устройство."""
    key = clean_str(gid, MAX_GID_LEN).lower()
    with lock:
        data = load_players()
    player = data.get(key)
    if not player:
        return jsonify({}), 404
    return jsonify(player)


@app.route('/api/players', methods=['POST'])
def post_player():
    entry = request.get_json(force=True, silent=True) or {}

    # Ключ гостя — его имя из картотеки, приведённое к нижнему регистру.
    # Именно поэтому один и тот же человек с телефона и с ноутбука
    # попадает в одну строку таблицы, а не в две.
    gid = clean_str(entry.get('gid'), MAX_GID_LEN).lower()
    if not gid:
        return jsonify({'ok': False, 'error': 'missing gid'}), 400

    try:
        caps = int(entry.get('caps', 0))
    except (TypeError, ValueError):
        caps = 0
    caps = max(0, min(caps, MAX_CAPS))

    with lock:
        data = load_players()

        # Защита от разрастания файла, если ссылку куда-то зашерят
        if gid not in data and len(data) >= MAX_PLAYERS:
            return jsonify({'ok': False, 'error': 'guest list full'}), 429

        existing = data.get(gid, {})
        existing['gid'] = gid
        existing['name'] = clean_str(entry.get('name'), MAX_NAME_LEN) or existing.get('name', 'Гость')
        existing['caps'] = caps

        # Телеграм: пустое поле НИКОГДА не затирает уже сохранённый ник.
        # Прислали непустой — перезаписываем. Прислали "-" — стираем намеренно.
        tg = clean_str(entry.get('tg'), MAX_TG_LEN)
        if tg == '-':
            existing.pop('tg', None)
        elif tg:
            existing['tg'] = tg

        data[gid] = existing
        save_players(data)

    return jsonify({'ok': True})


if __name__ == '__main__':
    # debug=False — иначе Flask показывает гостям трейсбеки и даёт консоль в браузере
    app.run(debug=False, port=5000)
