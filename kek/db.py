import sqlite3
import json

DB_NAME = "shop.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Позволяет обращаться к полям по имени
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Таблица товаров
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    brand TEXT,
    category TEXT,
    scent_type TEXT,   -- ← ВОТ ОНО
    description TEXT,
    volume TEXT,
    price REAL,
    photo TEXT,
    photo2 TEXT,
    notes_json TEXT,
    details_json TEXT
)
    """)

    # Таблица пользователей
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Таблица избранного
    c.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            product_id INTEGER,
            PRIMARY KEY (user_id, product_id)
        )
    """)

    # Таблица событий (статистика: start, order_click)
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT, -- 'start', 'order_click'
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

# Вспомогательные функции для бота и сайта
def get_all_products():
    conn = get_db()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    # Превращаем в список словарей, чтобы было похоже на старый data.py
    result = []
    for p in products:
        d = dict(p)
        if d['notes_json']: d['notes'] = json.loads(d['notes_json'])
        if d['details_json']: d.update(json.loads(d['details_json']))
        result.append(d)
    return result

def add_event(user_id, event_type):
    conn = get_db()
    conn.execute("INSERT INTO events (user_id, event_type) VALUES (?, ?)", (user_id, event_type))
    conn.commit()
    conn.close()

def toggle_favorite(user_id, product_id):
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?", (user_id, product_id)).fetchone()
    if exists:
        conn.execute("DELETE FROM favorites WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        res = False
    else:
        conn.execute("INSERT INTO favorites (user_id, product_id) VALUES (?, ?)", (user_id, product_id))
        res = True
    conn.commit()
    conn.close()
    return res

def get_user_stats(user_id):
    conn = get_db()
    fav_count = conn.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (user_id,)).fetchone()[0]
    order_clicks = conn.execute("SELECT COUNT(*) FROM events WHERE user_id = ? AND event_type = 'order_click'", (user_id,)).fetchone()[0]
    start_count = conn.execute("SELECT COUNT(*) FROM events WHERE user_id = ? AND event_type = 'start'", (user_id,)).fetchone()[0]
    conn.close()
    return {"favorites": fav_count, "orders": order_clicks, "starts": start_count}

if __name__ == "__main__":
    init_db()
    print("База данных инициализирована.")