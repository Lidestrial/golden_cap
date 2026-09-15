# Опциональный бэкенд для сайта-приглашения "Золотая крышка".
#
# ЗАЧЕМ ЭТО НУЖНО:
# Сайт внутри Claude.ai использует встроенное хранилище (window.storage), которое
# работает только внутри чата и общее только внутри одного артефакта. Если ты
# заливаешь invite-solo.html и invite-plus1.html как обычные файлы на свой хостинг —
# window.storage там не существует, и общая картотека (кто сколько крышек накопил,
# чьи телеграм оставлены) просто не будет сохраняться.
#
# Этот файл — маленький Flask-бэкенд с хранением в одном JSON-файле на диске.
# Сайт сам определяет, где он запущен: если window.storage есть — использует его
# (это происходит автоматически при просмотре в Claude), если нет — стучится сюда,
# на /api/players. Ничего в HTML-файлах менять не нужно.
#
# ЗАПУСК:
#   pip install flask
#   python app.py
# Открой http://127.0.0.1:5000/       — соло-версия
#       http://127.0.0.1:5000/plus1   — версия с +1
#
# Файл anthem.mp3 (украинский гимн, бас-буст) положи рядом с этим файлом —
# он отдаётся как обычный статический файл.

from flask import Flask, request, jsonify, send_from_directory
import json
import os
import threading

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'players.json')
lock = threading.Lock()


def load_players():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_players(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    return jsonify(list(data.values()))


@app.route('/api/players', methods=['POST'])
def post_player():
    entry = request.get_json(force=True, silent=True) or {}
    pid = entry.get('pid')
    if not pid:
        return jsonify({'ok': False, 'error': 'missing pid'}), 400

    with lock:
        data = load_players()
        existing = data.get(pid, {})
        existing['pid'] = pid
        existing['name'] = entry.get('name', existing.get('name', 'Гость'))
        existing['caps'] = entry.get('caps', existing.get('caps', 0))
        # Телеграм не затираем пустым значением, если его не прислали в этот раз
        if entry.get('tg'):
            existing['tg'] = entry.get('tg')
        data[pid] = existing
        save_players(data)

    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
