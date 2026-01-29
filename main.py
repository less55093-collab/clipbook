import sys
import os
from io import BytesIO

# --- Qt Imports ---
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QListWidget, QListWidgetItem, QTextEdit, QPushButton, 
                             QHBoxLayout, QLineEdit, QSystemTrayIcon, QMenu, QStyle,
                             QSplitter, QToolTip)
from PySide6.QtGui import QIcon, QPixmap, QAction, QCursor
from PySide6.QtCore import Qt, QThread, QSize

# --- Core Logic Imports ---
import database
from clipboard_monitor import ClipboardMonitor
import pyperclip
from PIL import Image
import startup

# --- Platform Specific Imports ---
import win32clipboard
import win32con

# --- Minimalist White Theme Stylesheet (Updated with Font and ToolTip) ---
LIGHT_STYLESHEET = """
QWidget {
    font-family: '等线 Light', 'Microsoft YaHei UI Light', 'Segoe UI Light', sans-serif;
    font-size: 10pt;
    color: #212121;
    background-color: #ffffff;
}
QMainWindow, QMenu {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
}
QListWidget {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 2px;
}
QListWidget::item {
    padding: 8px;
    border-radius: 3px;
    min-height: 30px;
}
QListWidget::item:hover {
    background-color: #f5f5f5;
}
QListWidget::item:selected {
    background-color: #e8f0fe;
    color: #1967d2;
}
QTextEdit, QLineEdit {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 6px;
}
QTextEdit:focus, QLineEdit:focus {
    border: 1px solid #8ab4f8;
}
QPushButton {
    background-color: #ffffff;
    color: #212121;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 8px 16px;
}
QPushButton:hover {
    background-color: #f8f8f8;
}
QPushButton:pressed {
    background-color: #f1f1f1;
}
QScrollBar:vertical {
    background: #fdfdfd;
    width: 12px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #e0e0e0;
    min-height: 20px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background: #d0d0d0;
}
QSplitter::handle:vertical {
    height: 1px;
    background-color: #e0e0e0;
}
QSplitter::handle:vertical:hover {
    background-color: #8ab4f8;
}
QMenu::item:selected {
    background-color: #f5f5f5;
}
QToolTip {
    color: #212121;
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 3px;
    padding: 4px 6px;
}
"""

def send_to_clipboard(clip_type, data):
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(clip_type, data)
    finally:
        win32clipboard.CloseClipboard()

class ClipboardHistoryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("剪贴板历史")
        self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation)))
        self.resize(400, 650)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("搜索历史...")
        self.layout.addWidget(self.search_bar)

        self.splitter = QSplitter(Qt.Vertical)
        self.layout.addWidget(self.splitter)

        self.history_list = QListWidget()
        self.history_list.setIconSize(QSize(48, 48))
        self.splitter.addWidget(self.history_list)

        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_item_context_menu)

        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.splitter.addWidget(self.preview_area)
        
        self.splitter.setSizes([400, 250])

        self.button_layout = QHBoxLayout()
        self.edit_button = QPushButton("编辑")
        self.delete_button = QPushButton("删除")
        self.hide_button = QPushButton("隐藏")
        self.button_layout.addWidget(self.edit_button)
        self.button_layout.addWidget(self.delete_button)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.hide_button)
        self.layout.addLayout(self.button_layout)
        
        self.history_list.itemDoubleClicked.connect(self.copy_item_to_clipboard)
        self.history_list.currentItemChanged.connect(self.update_preview)
        self.edit_button.clicked.connect(self.toggle_edit)
        self.delete_button.clicked.connect(self.delete_item)
        self.hide_button.clicked.connect(self.hide_to_tray)

        self.create_tray_icon()
        self.load_history()
        self.start_monitor_thread()

    def show_item_context_menu(self, position):
        item = self.history_list.itemAt(position)
        if not item:
            return

        menu = QMenu()
        copy_action = QAction("重新复制", self)
        copy_action.triggered.connect(lambda: self.copy_item_to_clipboard(item))
        menu.addAction(copy_action)
        
        menu.exec_(self.history_list.mapToGlobal(position))

    def start_monitor_thread(self):
        self.monitor_thread = QThread()
        self.clipboard_monitor = ClipboardMonitor()
        self.clipboard_monitor.moveToThread(self.monitor_thread)
        self.clipboard_monitor.newItemDetected.connect(self.load_history)
        self.monitor_thread.started.connect(self.clipboard_monitor.run)
        self.monitor_thread.start()

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.windowIcon())
        
        show_action = QAction("显示", self)
        self.startup_action = QAction("开机自启", self)
        self.startup_action.setCheckable(True)
        quit_action = QAction("退出", self)

        show_action.triggered.connect(self.show_window)
        self.startup_action.triggered.connect(self.toggle_startup)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        tray_menu = QMenu()
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(self.startup_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.update_startup_action_state()

    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def toggle_startup(self):
        if self.startup_action.isChecked():
            startup.add_to_startup()
        else:
            startup.remove_from_startup()
        self.update_startup_action_state()

    def update_startup_action_state(self):
        is_enabled = startup.is_in_startup()
        self.startup_action.setChecked(is_enabled)

    def load_history(self):
        current_id = None
        if self.history_list.currentItem():
            current_id = self.history_list.currentItem().data(Qt.UserRole)[0]

        self.history_list.clear()
        entries = database.get_all_entries()
        
        item_to_select = None
        for entry in entries:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry)
            
            if entry[1] == 'text':
                display_text = entry[2].strip().replace('\n', ' ')
                item.setText(display_text[:120] + '...' if len(display_text) > 120 else display_text)
            elif entry[1] == 'image' and os.path.exists(entry[2]):
                item.setText(f"[图片] {os.path.basename(entry[2])}")
                pixmap = QPixmap(entry[2])
                item.setIcon(QIcon(pixmap.scaled(self.history_list.iconSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            
            self.history_list.addItem(item)
            if entry[0] == current_id:
                item_to_select = item
        
        if item_to_select:
            self.history_list.setCurrentItem(item_to_select)

    def update_preview(self, current, previous):
        if not current:
            self.preview_area.clear()
            return
            
        entry = current.data(Qt.UserRole)
        entry_type, content = entry[1], entry[2]

        self.preview_area.setReadOnly(True)
        self.edit_button.setText("编辑")
        self.edit_button.setEnabled(entry_type == 'text')

        if entry_type == 'text':
            self.preview_area.setText(content)
        elif entry_type == 'image':
            if os.path.exists(content):
                self.preview_area.clear()
                self.preview_area.insertHtml(f'<img src="file:///{os.path.abspath(content)}" width="350">')
            else:
                self.preview_area.setText(f"[图片文件不存在: {content}]")

    def filter_list(self, text):
        search_text = text.lower()
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            item_text = item.text().lower()
            is_visible = not search_text or search_text in item_text
            item.setHidden(not is_visible)

    def copy_item_to_clipboard(self, item):
        entry = item.data(Qt.UserRole)
        entry_type, content = entry[1], entry[2]

        try:
            if entry_type == 'text':
                pyperclip.copy(content)
            elif entry_type == 'image':
                if not os.path.exists(content): return
                image = Image.open(content)
                output = BytesIO()
                image.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]
                output.close()
                send_to_clipboard(win32con.CF_DIB, data)

            QToolTip.showText(QCursor.pos(), "复制成功", msecShowTime=1000)

        except Exception as e:
            print(f"Error copying to clipboard: {e}")
            QToolTip.showText(QCursor.pos(), f"复制失败: {e}", msecShowTime=2000)

    def toggle_edit(self):
        current_item = self.history_list.currentItem()
        if not current_item or current_item.data(Qt.UserRole)[1] == 'image': return

        if self.preview_area.isReadOnly():
            self.preview_area.setReadOnly(False)
            self.edit_button.setText("保存")
            self.preview_area.setFocus()
        else:
            self.preview_area.setReadOnly(True)
            self.edit_button.setText("编辑")
            
            entry = current_item.data(Qt.UserRole)
            new_content = self.preview_area.toPlainText()
            database.update_entry(entry[0], new_content)
            self.load_history()

    def delete_item(self):
        current_item = self.history_list.currentItem()
        if not current_item: return
            
        entry = current_item.data(Qt.UserRole)
        database.delete_entry(entry[0])
        
        if entry[1] == 'image' and os.path.exists(entry[2]):
            try:
                os.remove(entry[2])
            except OSError as e:
                print(f"Error deleting image file: {e}")
                
        self.load_history()

    def hide_to_tray(self):
        self.hide()
        QToolTip.showText(QCursor.pos(), "已隐藏到系统托盘", msecShowTime=1500)

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_tray()

if __name__ == '__main__':
    database.init_db()

    app = QApplication(sys.argv)
    app.setStyleSheet(LIGHT_STYLESHEET)
    app.setQuitOnLastWindowClosed(False) 
    
    window = ClipboardHistoryApp()
    window.show()

    sys.exit(app.exec())
