import os
import json

# 数据库文件名
DB_NAME = "clipboard_history.db"

# 获取应用数据目录，用于存放数据库和图片
APP_DATA_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'ClipboardHistory')

# 确保应用数据目录存在
if not os.path.exists(APP_DATA_DIR):
    os.makedirs(APP_DATA_DIR)

# 数据库文件的完整路径
DATABASE_PATH = os.path.join(APP_DATA_DIR, DB_NAME)

# 存储图片的目录
IMAGE_DIR = os.path.join(APP_DATA_DIR, 'images')

# 确保图片目录存在
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# 设置文件路径
SETTINGS_PATH = os.path.join(APP_DATA_DIR, 'settings.json')

# 默认设置
DEFAULT_SETTINGS = {
    'auto_clean_enabled': False,
    'auto_clean_days': 10,
    'last_clean_date': None,
    'hotkey': 'ctrl+shift+v'
}

def load_settings():
    """加载设置"""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # 合并默认设置（确保新增的设置项有默认值）
                return {**DEFAULT_SETTINGS, **settings}
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """保存设置"""
    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

