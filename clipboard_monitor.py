import time
import pyperclip
from PIL import ImageGrab
import os
from io import BytesIO
import hashlib

import database
from config import IMAGE_DIR
from PySide6.QtCore import QObject, Signal

class ClipboardMonitor(QObject):
    """
    一个在后台运行的QObject，用于监控剪贴板。
    当有新内容时，会发出 newItemDetected 信号。
    """
    newItemDetected = Signal()

    def __init__(self):
        super().__init__()
        self.last_hash = None

    def get_clipboard_hash(self, data):
        """计算数据的MD5哈希值"""
        if isinstance(data, str):
            return hashlib.md5(data.encode('utf-8')).hexdigest()
        elif isinstance(data, bytes):
            return hashlib.md5(data).hexdigest()
        return None

    def run(self):
        """开始循环监控剪贴板"""
        print("Clipboard monitor started...")
        while True:
            try:
                # 尝试获取图片
                image = ImageGrab.grabclipboard()
                if image:
                    buffer = BytesIO()
                    image.save(buffer, format='PNG')
                    img_bytes = buffer.getvalue()
                    current_hash = self.get_clipboard_hash(img_bytes)

                    if current_hash != self.last_hash:
                        # 对于图片，我们不合并，总是添加新的
                        filename = f"{int(time.time())}_{current_hash[:10]}.png"
                        filepath = os.path.join(IMAGE_DIR, filename)
                        image.save(filepath)
                        
                        database.add_entry('image', filepath)
                        self.last_hash = current_hash
                        print(f"Image saved: {filepath}")
                        self.newItemDetected.emit()
                    continue

                # 如果不是图片，尝试获取文本
                text = pyperclip.paste()
                if text and isinstance(text, str):
                    current_hash = self.get_clipboard_hash(text)
                    if current_hash != self.last_hash:
                        # --- 合并逻辑 ---
                        # 1. 先删除数据库中任何已存在的相同内容
                        database.delete_entry_by_content(text)
                        
                        # 2. 再添加新的记录（这样它就有了最新的时间戳）
                        database.add_entry('text', text)
                        
                        self.last_hash = current_hash
                        print(f"Text entry updated/added: {text[:50]}...")
                        self.newItemDetected.emit()

            except Exception as e:
                pass
            
            time.sleep(1)
