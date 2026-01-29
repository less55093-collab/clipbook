import sqlite3
from config import DATABASE_PATH

def init_db():
    """初始化数据库，创建表"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clipboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, -- 'text' or 'image'
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_entry(entry_type, content):
    """向数据库添加新条目"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO clipboard (type, content) VALUES (?, ?)", (entry_type, content))
    conn.commit()
    conn.close()

def get_all_entries():
    """获取所有历史记录"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, content, timestamp FROM clipboard ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_entry(entry_id, new_content):
    """更新指定ID的条目内容"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE clipboard SET content = ? WHERE id = ?", (new_content, entry_id))
    conn.commit()
    conn.close()

def delete_entry(entry_id):
    """删除指定ID的条目"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clipboard WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

def delete_entry_by_content(content):
    """根据内容删除文本条目，用于合并重复项"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    # 仅对 'text' 类型的条目执行此操作
    cursor.execute("DELETE FROM clipboard WHERE type = 'text' AND content = ?", (content,))
    conn.commit()
    conn.close()

# 在模块首次导入时初始化数据库
init_db()
