import sqlite3
import threading
from config import DATABASE_PATH

# --- 单例连接 + 线程锁 ---
_connection = None
_lock = threading.Lock()


def get_connection():
    """获取复用的数据库连接（线程安全）"""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL")  # WAL 模式提升并发性能
        _connection.execute("PRAGMA synchronous=NORMAL")  # 减少磁盘同步等待
    return _connection


def init_db():
    """初始化数据库，创建表"""
    with _lock:
        conn = get_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS clipboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL, -- 'text' or 'image'
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()


def add_entry(entry_type, content):
    """向数据库添加新条目，返回新条目的完整数据"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO clipboard (type, content) VALUES (?, ?)", (entry_type, content))
        conn.commit()
        # 返回刚插入的完整记录
        entry_id = cursor.lastrowid
        cursor.execute("SELECT id, type, content, timestamp FROM clipboard WHERE id = ?", (entry_id,))
        return cursor.fetchone()


def get_all_entries():
    """获取所有历史记录"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, type, content, timestamp FROM clipboard ORDER BY timestamp DESC")
        return cursor.fetchall()


def get_entries_paged(limit, offset=0):
    """分页获取历史记录"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, type, content, timestamp FROM clipboard ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return cursor.fetchall()


def get_total_count():
    """获取记录总数"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clipboard")
        return cursor.fetchone()[0]


def update_entry(entry_id, new_content):
    """更新指定ID的条目内容"""
    with _lock:
        conn = get_connection()
        conn.execute("UPDATE clipboard SET content = ? WHERE id = ?", (new_content, entry_id))
        conn.commit()


def delete_entry(entry_id):
    """删除指定ID的条目"""
    with _lock:
        conn = get_connection()
        conn.execute("DELETE FROM clipboard WHERE id = ?", (entry_id,))
        conn.commit()


def delete_entry_by_content(content):
    """根据内容删除文本条目，用于合并重复项。返回被删除的条目数。"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clipboard WHERE type = 'text' AND content = ?", (content,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


def delete_image_by_hash(hash_substr):
    """
    根据哈希片段删除图片条目（用于合并重复图片）。
    返回被删除的图片路径列表，以便后续从磁盘清理。
    """
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()

        query_pattern = f'%_{hash_substr}.png'
        cursor.execute("SELECT content FROM clipboard WHERE type = 'image' AND content LIKE ?", (query_pattern,))
        rows = cursor.fetchall()

        deleted_files = [row[0] for row in rows]

        if deleted_files:
            cursor.execute("DELETE FROM clipboard WHERE type = 'image' AND content LIKE ?", (query_pattern,))
            conn.commit()

        return deleted_files


def get_entries_before_date(date_str):
    """获取指定日期之前的所有条目"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, type, content, timestamp FROM clipboard WHERE timestamp < ?", (date_str,))
        return cursor.fetchall()


def delete_entries_before_date(date_str):
    """删除指定日期之前的所有条目"""
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clipboard WHERE timestamp < ?", (date_str,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


# 在模块首次导入时初始化数据库
init_db()
