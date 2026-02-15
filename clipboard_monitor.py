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
    当有新内容时，会发出携带数据的增量信号。
    """
    # 增量信号：携带新条目的完整数据 (id, type, content, timestamp)
    newEntryDetected = Signal(tuple)
    # 全量刷新信号：用于需要重建列表的场景（如合并重复时删除了旧卡片）
    fullRefreshNeeded = Signal()

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
                        hash_substr = current_hash[:10]
                        deleted_files = database.delete_image_by_hash(hash_substr)
                        had_duplicates = len(deleted_files) > 0

                        # 清理磁盘上的旧文件
                        for fpath in deleted_files:
                            try:
                                if os.path.exists(fpath):
                                    os.remove(fpath)
                                print(f"Removed duplicate image: {fpath}")
                            except Exception as e:
                                print(f"Error removing file {fpath}: {e}")

                        # 保存新图片
                        filename = f"{int(time.time())}_{hash_substr}.png"
                        filepath = os.path.join(IMAGE_DIR, filename)
                        image.save(filepath)

                        new_entry = database.add_entry('image', filepath)
                        self.last_hash = current_hash
                        print(f"Image saved: {filepath}")

                        if had_duplicates:
                            # 有重复项被删除，需要全量刷新以同步 UI
                            self.fullRefreshNeeded.emit()
                        else:
                            # 纯新增，增量更新
                            self.newEntryDetected.emit(new_entry)
                    continue

                # 如果不是图片，尝试获取文本
                text = pyperclip.paste()
                if text and isinstance(text, str):
                    current_hash = self.get_clipboard_hash(text)
                    if current_hash != self.last_hash:
                        # 合并逻辑：先删除已存在的相同内容
                        deleted_count = database.delete_entry_by_content(text)

                        # 再添加新记录
                        new_entry = database.add_entry('text', text)
                        self.last_hash = current_hash
                        print(f"Text entry updated/added: {text[:50]}...")

                        if deleted_count > 0:
                            # 有旧记录被删除，全量刷新
                            self.fullRefreshNeeded.emit()
                        else:
                            # 纯新增，增量更新
                            self.newEntryDetected.emit(new_entry)

            except Exception as e:
                pass

            time.sleep(1)
