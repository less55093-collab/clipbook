import os

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
