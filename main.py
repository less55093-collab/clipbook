import sys
import os
import time

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QFileDialog, QSystemTrayIcon, QMenu, QLabel, QScrollArea, QDialog, QDialogButtonBox
from PySide6.QtCore import Qt, Signal, QUrl, QSize, QTimer, QThread, QPoint, QMimeData, QEasingCurve
from PySide6.QtGui import QIcon, QDesktopServices, QPixmap, QAction, QCursor, QDrag, QColor, QPalette, QPixmapCache

from qfluentwidgets import (MSFluentWindow, NavigationItemPosition, 
                            SubtitleLabel, CardWidget, ImageLabel, BodyLabel, 
                            TransparentToolButton, SearchLineEdit, PrimaryPushButton, 
                            SmoothScrollArea, FlowLayout, FluentIcon as FIF,
                            SwitchSettingCard, PushSettingCard, SettingCardGroup,
                            InfoBar, InfoBarPosition, ScrollArea,
                            TextEdit, PlainTextEdit, Flyout, FlyoutAnimationType,
                            setTheme, setThemeColor, Theme)

# 默认快捷键
DEFAULT_HOTKEY = 'ctrl+shift+v'

import database
import startup
from clipboard_monitor import ClipboardMonitor
import pyperclip
from PIL import Image
from io import BytesIO
import win32clipboard
import win32con
from config import load_settings, save_settings, IMAGE_DIR
from datetime import datetime, timedelta
import keyboard  # 用于快捷键录制
import ctypes
from ctypes import wintypes

def resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和 PyInstaller 打包环境"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def parse_hotkey(hotkey_str):
    """
    解析快捷键字符串 (e.g., 'ctrl+shift+v') 为 (modifiers, vk_code)
    """
    if not hotkey_str:
        return 0, 0
        
    hotkey_str = hotkey_str.lower().replace(" ", "")
    parts = hotkey_str.split('+')
    
    modifiers = 0
    vk_code = 0
    
    # Modifier constants
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000
    
    mod_map = {
        'ctrl': MOD_CONTROL,
        'control': MOD_CONTROL,
        'shift': MOD_SHIFT,
        'alt': MOD_ALT,
        'win': MOD_WIN,
        'windows': MOD_WIN,
        'meta': MOD_WIN
    }
    
    # VK codes needed for mapping
    # 常用键位映射
    key_map = {
        'backspace': win32con.VK_BACK,
        'tab': win32con.VK_TAB,
        'clear': win32con.VK_CLEAR,
        'enter': win32con.VK_RETURN,
        'return': win32con.VK_RETURN,
        'shift': win32con.VK_SHIFT,
        'ctrl': win32con.VK_CONTROL,
        'control': win32con.VK_CONTROL,
        'alt': win32con.VK_MENU,
        'pause': win32con.VK_PAUSE,
        'capslock': win32con.VK_CAPITAL,
        'esc': win32con.VK_ESCAPE,
        'escape': win32con.VK_ESCAPE,
        'space': win32con.VK_SPACE,
        'pageup': win32con.VK_PRIOR,
        'pagedown': win32con.VK_NEXT,
        'end': win32con.VK_END,
        'home': win32con.VK_HOME,
        'left': win32con.VK_LEFT,
        'up': win32con.VK_UP,
        'right': win32con.VK_RIGHT,
        'down': win32con.VK_DOWN,
        'printscreen': win32con.VK_PRINT,
        'insert': win32con.VK_INSERT,
        'delete': win32con.VK_DELETE,
        'help': win32con.VK_HELP,
        # F1-F24
        'numlock': win32con.VK_NUMLOCK,
        'scrolllock': win32con.VK_SCROLL,
    }
    
    # Handle F1-F12
    for i in range(1, 25):
        key_map[f'f{i}'] = getattr(win32con, f'VK_F{i}', 0x70 + i - 1)
        
    user32 = ctypes.windll.user32
    
    for part in parts:
        if part in mod_map:
            modifiers |= mod_map[part]
        elif part in key_map:
            vk_code = key_map[part]
        elif len(part) == 1:
            # 单字符，获取 VK Code
            # VkKeyScanW 返回 short，低字节为 VK Code
            vk = user32.VkKeyScanW(ord(part))
            if vk != -1:
                vk_code = vk & 0xFF
            else:
                # 尝试大写
                vk = user32.VkKeyScanW(ord(part.upper()))
                if vk != -1:
                    vk_code = vk & 0xFF
    
    return modifiers | MOD_NOREPEAT, vk_code


def send_to_clipboard(clip_type, data):
    """发送数据到剪贴板，带有重试机制"""
    # 尝试打开剪贴板（重试 5 次）
    for i in range(5):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception:
            if i == 4:
                raise # 最后一次尝试也失败，抛出异常
            time.sleep(0.1)

    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(clip_type, data)
    finally:
        # OpenClipboard 成功后才需要 Close
        # 如果 OpenClipboard 在上面 raise 了，这里不会执行
        win32clipboard.CloseClipboard()


class EditableBlock(PlainTextEdit):
    """能够直接编辑、自动保存、并传递滚轮事件的文本框"""
    focusOut = Signal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setPlainText(text)

        # 莫兰迪色调样式
        self.setStyleSheet("""
            PlainTextEdit, QPlainTextEdit {
                background-color: transparent;
                border: none;
                padding: 0px;
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 9pt;
                color: #4A4543;  /* 莫兰迪深灰褐 */
            }
        """)
        # 允许垂直滚动
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
    def focusOutEvent(self, event):
        # 失去焦点时发送信号，触发保存
        super().focusOutEvent(event)
        self.focusOut.emit(self.toPlainText())

    def wheelEvent(self, event):
        # 没有焦点时，直接把滚轮事件转发给最外层的滚动区域
        if not self.hasFocus():
            # 找到父级的 ScrollArea 并把事件发给它
            parent = self.parent()
            while parent:
                if hasattr(parent, 'verticalScrollBar') and parent.__class__.__name__ in ('ScrollArea', 'SmoothScrollArea', 'QScrollArea'):
                    # 找到滚动区域，转发事件
                    QApplication.sendEvent(parent.viewport(), event)
                    return
                parent = parent.parent() if hasattr(parent, 'parent') else None
            # 没找到滚动区域，忽略事件
            event.ignore()
            return
            
        # 有焦点时，正常处理滚轮事件
        # 如果滚到头了，让父控件（整个页面）滚动
        vbar = self.verticalScrollBar()
        is_top = (vbar.value() == vbar.minimum())
        is_bottom = (vbar.value() == vbar.maximum())
        angle = event.angleDelta().y()

        if (angle > 0 and is_top) or (angle < 0 and is_bottom):
            # 滚到头了，转发给滚动区域
            parent = self.parent()
            while parent:
                if hasattr(parent, 'verticalScrollBar') and parent.__class__.__name__ in ('ScrollArea', 'SmoothScrollArea', 'QScrollArea'):
                    QApplication.sendEvent(parent.viewport(), event)
                    return
                parent = parent.parent() if hasattr(parent, 'parent') else None
            event.ignore()
        else:
            event.accept()
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        # 1. 处理原本的文本光标/选区逻辑
        super().mousePressEvent(event)
        
        # 2. 通知父级卡片“哪怕点的是文本框，卡片也被点击了”
        if hasattr(self.parent(), 'clicked'):
            self.parent().clicked.emit(self.parent())
            
        # 3. 记录拖拽起始点 (如果是左键) - 如果需要支持从文本框开始拖拽这个卡片
        # 注意：这会和文本选区冲突。这里优先保留文本选区功能，因此我们**不**在这里启动卡片拖拽。
        # 如果用户想拖拽卡片，需要点击卡片边缘。


    def contextMenuEvent(self, event):
        # 右键点击时：
        # 1. 先保存当前内容，确保复制的是最新文本
        if hasattr(self.parent(), 'save_content'):
            self.parent().save_content(self.toPlainText())
            
        # 2. 转发给 Card 组件，弹出统一的菜单（包含复制、删除等）
        if hasattr(self.parent(), 'rightClicked'):
             self.parent().rightClicked.emit(self.parent(), event.globalPos())


class ClipboardCard(CardWidget):
    """剪贴板卡片组件 - 支持拖拽版"""
    clicked = Signal(object)
    doubleClicked = Signal(object)
    rightClicked = Signal(object, object)
    
    # 类级别共享样式表，避免每个实例重复创建字符串
    CARD_STYLESHEET = """
        /* 默认状态 - 纯白底 + 浅灰边框 */
        ClipboardCard {
            border: 1px solid #E0E0E0;
            background-color: #FFFFFF;
            border-radius: 8px;
        }
        
        /* 悬停状态 - 稍深的灰边框 */
        ClipboardCard[selected="false"]:hover {
            background-color: #F8F8F8;
            border: 1px solid #CCCCCC;
        }

        /* 选中状态 - 蓝色细边框 */
        ClipboardCard[selected="true"] {
            border: 1px solid #0078D4;
            background-color: rgba(0, 120, 212, 0.05);
        }"""
    
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.is_selected = False
        self.drag_start_pos = None  # 用于记录拖拽起始点
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(160, 160)
        self.setCursor(Qt.PointingHandCursor)
        
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)
        self.setStyleSheet(self.CARD_STYLESHEET)
        self.setup_content()
        self.setSelected(False)

    def setSelected(self, is_selected):
        self.is_selected = is_selected
        self.setProperty("selected", is_selected)
        # 2. 【关键】强制刷新样式
        # 改变属性后，Qt 不会自动重绘样式，必须手动 polich (打磨) 一下
        self.style().unpolish(self)
        self.style().polish(self)
    def mousePressEvent(self, event):
        # 判断是否是鼠标**左键**点击
        if event.button() == Qt.LeftButton:
            # 左键点击时，强制设置为选中状态（永久保持）
            self.setSelected(True)
            self.clicked.emit(self.entry)
        # 保留父类的鼠标事件行为（避免屏蔽其他鼠标操作，必加）
        super().mousePressEvent(event)    
    def setup_content(self):
        entry_type = self.entry[1]
        content = self.entry[2]
        
        # 调整布局边距，让内容更靠近边缘，利用率更高
        # 参数顺序：左，上，右，下
        self.vBoxLayout.setContentsMargins(12, 12, 12, 12)
        
        if entry_type == 'image' and os.path.exists(content):
            self.imageLabel = ImageLabel(content, self)
            self.imageLabel.setBorderRadius(8, 8, 8, 8)
            self.imageLabel.setFixedSize(136, 136)
            
            # 图片缩略图缓存：避免每次重新从磁盘加载和缩放
            cache_key = f"thumb_{content}"
            cached_pixmap = QPixmapCache.find(cache_key)
            if cached_pixmap and not cached_pixmap.isNull():
                self.imageLabel.setPixmap(cached_pixmap)
            else:
                pixmap = QPixmap(content)
                if not pixmap.isNull():
                    thumbnail = pixmap.scaled(
                        136, 136, 
                        Qt.KeepAspectRatio, 
                        Qt.SmoothTransformation
                    )
                    QPixmapCache.insert(cache_key, thumbnail)
                    self.imageLabel.setPixmap(thumbnail)
            
            self.vBoxLayout.addWidget(self.imageLabel, 0, Qt.AlignCenter)
        elif entry_type == 'text':

            # 直接使用可编辑的文本框替代 Label
            self.contentEdit = EditableBlock(content, self)
            
            # 绑定失去焦点时的保存信号
            self.contentEdit.focusOut.connect(self.save_content)
            
            # 设置伸缩因子为 1，占据所有可用空间
            self.vBoxLayout.addWidget(self.contentEdit, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos() # 1. 记录按下位置
            self.clicked.emit(self)
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self, event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 2. 检测是否正在按住左键移动
        if not (event.buttons() & Qt.LeftButton):
            return
        if not self.drag_start_pos:
            return
            
        # 计算移动距离，防止手抖误触发
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        # 3. 开始构建拖拽数据
        drag = QDrag(self)
        mime_data = QMimeData()
        
        entry_type = self.entry[1]
        content = self.entry[2]

        if entry_type == 'image' and os.path.exists(content):
            # --- 关键：图片拖拽 ---
            # 要拖到桌面变成文件，或者拖到微信，必须设置为 URL 列表
            url = QUrl.fromLocalFile(os.path.abspath(content))
            mime_data.setUrls([url])
        elif entry_type == 'text':
            # --- 文本拖拽 ---
            mime_data.setText(content)
        else:
            return # 无效内容不拖拽

        drag.setMimeData(mime_data)

        # 4. 设置拖拽时的视觉效果（半透明的卡片截图）
        pixmap = self.grab() # 截取当前卡片的画面
        drag.setPixmap(pixmap)
        
        # 设置鼠标在截图上的位置（保持抓取点一致）
        drag.setHotSpot(event.pos())

        # 5. 执行拖拽（阻塞直到松手）
        drag.exec(Qt.CopyAction | Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        # 双击仍然可以触发复制，或者留空（因为现在单击就可以编辑了）
        # 这里保留双击复制逻辑作为快捷操作
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self)
        super().mouseDoubleClickEvent(event)
        
    def save_content(self, new_text):
        """自动保存内容到数据库"""
        if new_text != self.entry[2]:
            database.update_entry(self.entry[0], new_text)
            # 更新内存中的 entry 数据，保持同步
            self.entry = (self.entry[0], self.entry[1], new_text)
            print(f"Auto-saved entry {self.entry[0]}")


# --- 莫兰迪色调 Stylesheet ---
# 莫兰迪色系：低饱和度、灰调柔和的高级配色
MORANDI_COLORS = {
    'bg_primary': '#E8E4E1',      # 主背景 - 温暖米灰
    'bg_secondary': '#D5CEC8',    # 次级背景 - 灰褐
    'bg_card': '#F5F2EF',         # 卡片背景 - 奶白
    'bg_card_hover': '#EBE7E3',   # 卡片悬停 - 浅灰米
    'accent': '#9B8578',          # 强调色 - 莫兰迪棕
    'accent_light': '#B8A99A',    # 浅强调 - 灰驼色
    'accent_selected': '#8B9A8B', # 选中色 - 莫兰迪绿
    'text_primary': '#4A4543',    # 主文本 - 深灰褐
    'text_secondary': '#7A7572',  # 次级文本 - 中灰
    'border': '#C5BEB7',          # 边框 - 灰米
    'border_light': '#DDD8D3',    # 浅边框
}

MODERN_STYLESHEET = """
QWidget {
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
    font-size: 9pt;
    color: #4A4543;
}

/* 主窗口背景 - 浅灰色 */
MSFluentWindow {
    background-color: #F5F5F5;
    border: none;
}

/* 导航栏 - 与主背景统一 */
NavigationInterface {
    background-color: #F5F5F5;
    border: none;
}

/* 导航按钮样式 */
NavigationPushButton {
    background-color: transparent;
    border-radius: 6px;
    margin: 4px 8px;
}

NavigationPushButton:hover {
    background-color: rgba(155, 133, 120, 0.15);
}

NavigationPushButton:pressed {
    background-color: rgba(155, 133, 120, 0.25);
}

/* 右侧内容区域 */
QStackedWidget {
    background-color: transparent;
    border: none;
}

/* 滚动区域和子界面 */
#scrollWidget, #clipboardInterface, #settingsInterface {
    background-color: transparent;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

/* 搜索框 - 简洁白色风格 */
SearchLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
    padding: 6px 12px;
    color: #333333;
}

SearchLineEdit:focus {
    border: 1px solid #0078D4;
    background-color: #FFFFFF;
}

/* 滚动条样式 */
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #B8A99A;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #9B8578;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* 设置卡片组 */
SettingCardGroup {
    background-color: transparent;
}

/* 设置卡片 */
SettingCard {
    background-color: #F5F2EF;
    border: 1px solid #DDD8D3;
    border-radius: 10px;
}

SettingCard:hover {
    background-color: #EBE7E3;
    border: 1px solid #C5BEB7;
}

/* 开关按钮 - qfluentwidgets 的 SwitchButton 不支持 CSS 颜色自定义 */

/* 按钮样式 */
PushButton, PrimaryPushButton {
    background-color: #9B8578;
    color: #FFFEFB;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
}

PushButton:hover, PrimaryPushButton:hover {
    background-color: #8A7568;
}

PushButton:pressed, PrimaryPushButton:pressed {
    background-color: #7A6558;
}

/* 透明工具按钮 */
TransparentToolButton {
    background-color: transparent;
    border-radius: 6px;
}

TransparentToolButton:hover {
    background-color: rgba(155, 133, 120, 0.15);
}

/* 信息提示条 */
InfoBar {
    background-color: #F5F2EF;
    border: 1px solid #C5BEB7;
    border-radius: 8px;
}

/* 滑块 */
Slider::groove:horizontal {
    background-color: #D5CEC8;
    height: 4px;
    border-radius: 2px;
}

Slider::handle:horizontal {
    background-color: #9B8578;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -6px 0;
}

Slider::sub-page:horizontal {
    background-color: #8B9A8B;
    border-radius: 2px;
}
"""


class ClipboardInterface(QWidget):
    """剪贴板历史界面"""
    
    PAGE_SIZE = 50  # 每页加载的卡片数量
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self._loaded_count = 0  # 已加载的条目数量
        self._all_loaded = False  # 是否所有条目已加载
        self._loading = False  # 防止重复触发加载
        self.setObjectName("clipboardInterface")
        self.setStyleSheet("background-color: transparent;")
        
        # 限制 QPixmapCache 大小，防止图片缩略图无限占内存（默认 10240 KB = 10MB）
        QPixmapCache.setCacheLimit(51200)  # 50 MB
        
        # 1. 创建总布局 (垂直排列：搜索栏在顶，卡片列表在下)
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(30, 20, 30, 20)
        self.mainLayout.setSpacing(15)
        
        # 2. 创建搜索和操作区域 (Header)
        self.headerLayout = QHBoxLayout()
        
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索剪贴板...")
        self.searchEdit.setFixedWidth(300)
        self.searchEdit.textChanged.connect(self.filter_cards)
        
        self.deleteBtn = TransparentToolButton(FIF.DELETE, self)
        self.deleteBtn.setToolTip("删除选中")
        self.deleteBtn.clicked.connect(self.on_delete_clicked)
        
        self.headerLayout.addWidget(self.searchEdit)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.deleteBtn)
        
        self.mainLayout.addLayout(self.headerLayout)
        
        # 3. 滚动区域 — 使用原生 QScrollArea，滚动直接跟手，无动画延迟
        self.scrollArea = QScrollArea(self)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setFrameShape(QFrame.NoFrame)
        self.scrollArea.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        self.scrollArea.viewport().setStyleSheet("background-color: transparent;")
        
        # 卡片容器
        self.cardsContainer = QWidget()
        self.cardsContainer.setStyleSheet("background-color: transparent;")
        self.cardsLayout = FlowLayout(self.cardsContainer)
        self.cardsLayout.setContentsMargins(0, 0, 0, 0)
        self.cardsLayout.setVerticalSpacing(10)
        self.cardsLayout.setHorizontalSpacing(10)
        
        self.scrollArea.setWidget(self.cardsContainer)
        self.mainLayout.addWidget(self.scrollArea)
        
        # 4. 滚动到底部时自动加载更多
        self.scrollArea.verticalScrollBar().valueChanged.connect(self._on_scroll)


    def _on_scroll(self, value):
        """滚动条变化时检测是否接近底部，触发加载更多"""
        if self._all_loaded or self._loading:
            return
        scrollbar = self.scrollArea.verticalScrollBar()
        # 当滚动到距底部不到 200px 时加载更多
        if scrollbar.maximum() - value < 200:
            self.load_more_cards()

    def on_delete_clicked(self):
        selected_cards = [card for card in self.cards if card.is_selected]
        
        if not selected_cards:
            InfoBar.warning(
                title="未选中",
                content="请先点击卡片以选择要删除的内容。",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
            return

        # 如果有选中的，执行删除
        count = len(selected_cards)
        for card in selected_cards:
            self.delete_card(card, auto_fill=False)
            
        # 手动触发一次滚动检查，以便自动加载填补空缺 (0ms 立即执行)
        QTimer.singleShot(0, lambda: self._on_scroll(self.scrollArea.verticalScrollBar().value()))
            
        InfoBar.success("删除成功", f"已删除 {count} 个项目。", parent=self)


    def load_history(self):
        """全量重载：清空后分页加载第一批"""
        self.cardsContainer.setVisible(False)
        
        # Clear existing
        for i in reversed(range(self.cardsLayout.count())):
            widget = self.cardsLayout.itemAt(i).widget()
            if widget:
                self.cardsLayout.removeWidget(widget)
                widget.deleteLater()
        self.cards.clear()
        self._loaded_count = 0
        self._all_loaded = False
        
        # 只加载第一页
        entries = database.get_entries_paged(self.PAGE_SIZE, 0)
        for entry in entries:
            card = ClipboardCard(entry)
            card.clicked.connect(self.on_card_clicked)
            card.doubleClicked.connect(self.copy_item)
            card.rightClicked.connect(self.show_context_menu)
            
            self.cardsLayout.addWidget(card)
            self.cards.append(card)
        
        self._loaded_count = len(entries)
        if len(entries) < self.PAGE_SIZE:
            self._all_loaded = True
        
        self.cardsContainer.setVisible(True)

    def load_more_cards(self):
        """滚动到底部时，加载下一页卡片"""
        if self._all_loaded or self._loading:
            return
        
        self._loading = True
        entries = database.get_entries_paged(self.PAGE_SIZE, self._loaded_count)
        
        for entry in entries:
            card = ClipboardCard(entry)
            card.clicked.connect(self.on_card_clicked)
            card.doubleClicked.connect(self.copy_item)
            card.rightClicked.connect(self.show_context_menu)
            
            self.cardsLayout.addWidget(card)
            self.cards.append(card)
        
        self._loaded_count += len(entries)
        if len(entries) < self.PAGE_SIZE:
            self._all_loaded = True
        
        self._loading = False

    def add_card_to_front(self, entry):
        """在列表最前面插入一张新卡片（增量更新，不重建整个列表）"""
        card = ClipboardCard(entry)
        card.clicked.connect(self.on_card_clicked)
        card.doubleClicked.connect(self.copy_item)
        card.rightClicked.connect(self.show_context_menu)
        
        self.cards.insert(0, card)
        self._loaded_count += 1
        
        # 重建布局顺序
        for i in reversed(range(self.cardsLayout.count())):
            item = self.cardsLayout.itemAt(i)
            if item and item.widget():
                self.cardsLayout.removeWidget(item.widget())
        
        for c in self.cards:
            self.cardsLayout.addWidget(c)

    def on_new_entry(self, entry):
        """收到新剪贴板条目的槽函数（增量更新）"""
        self.add_card_to_front(entry)

    def on_card_clicked(self, card):
        # 切换选中状态
        card.setSelected(not card.is_selected)

    def copy_item(self, card):
        entry = card.entry
        try:
            if entry[1] == 'text':
                # 文本复制增加重试机制
                for i in range(5):
                    try:
                        pyperclip.copy(entry[2])
                        break
                    except Exception:
                        if i == 4:
                            raise
                        time.sleep(0.1)
                        
            elif entry[1] == 'image':
                 if os.path.exists(entry[2]):
                    image = Image.open(entry[2])
                    output = BytesIO()
                    image.convert("RGB").save(output, "BMP")
                    data = output.getvalue()[14:]
                    output.close()
                    send_to_clipboard(win32con.CF_DIB, data)
            
            InfoBar.success(
                title='复制成功',
                content='内容已复制到剪贴板',
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
        except Exception as e:
            InfoBar.error(
                title='复制失败',
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

    def show_context_menu(self, card, pos):
        menu = QMenu(self)
        
        action_copy = QAction(FIF.COPY.icon(), "复制", self)
        action_copy.triggered.connect(lambda: self.copy_item(card))
        menu.addAction(action_copy)
        
        # (已移除 '编辑' 选项，因为现在支持直接点击编辑)
            
        menu.addSeparator()
        
        action_delete = QAction(FIF.DELETE.icon(), "删除", self)
        action_delete.triggered.connect(lambda: self.delete_card(card))
        menu.addAction(action_delete)
        
        menu.exec_(pos)

    def delete_card(self, card, auto_fill=True):
        """删除卡片，并可选通过 auto_fill 参数触发自动填充"""
        entry = card.entry
        
        # 1. 先从界面移除并销毁组件，释放潜在的文件占用
        card.hide() # 立即隐藏，确保布局立即刷新
        self.cardsLayout.removeWidget(card)
        card.deleteLater()
        if card in self.cards:
            self.cards.remove(card)
            self._loaded_count = max(0, self._loaded_count - 1)
            # 重置分页标记，允许滚动时补充卡片
            self._all_loaded = False
        
        # 如果需要自动填充（默认 True，批量删除时设为 False）
        if auto_fill:
            QTimer.singleShot(0, lambda: self._on_scroll(self.scrollArea.verticalScrollBar().value()))
            
        # 2. 处理数据库
        database.delete_entry(entry[0])
        
        # 3. 稍微延时或直接尝试删除文件
        if entry[1] == 'image' and os.path.exists(entry[2]):
            try:
                os.remove(entry[2])
            except PermissionError:
                print(f"文件正在被使用，无法删除: {entry[2]}")
            except Exception as e:
                print(e)

    def filter_cards(self, text):
        search_text = text.lower()
        for card in self.cards:
            entry = card.entry
            visible = True
            if entry[1] == 'text':
                if search_text and search_text not in entry[2].lower():
                    visible = False
            else:
                if search_text:
                    visible = False # Hide images when searching text
            
            card.setVisible(visible)

from qfluentwidgets import RangeSettingCard, CalendarPicker, SettingCard, Slider


class HotkeyRecordDialog(QDialog):
    """快捷键录制对话框 — 使用 Qt 原生按键事件捕获组合键"""

    # Qt 修饰键映射到 keyboard 库格式的名称
    _MOD_MAP = {
        Qt.Key_Control: 'ctrl',
        Qt.Key_Shift: 'shift',
        Qt.Key_Alt: 'alt',
        Qt.Key_Meta: 'win',
    }

    def __init__(self, current_hotkey='', parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置全局快捷键")
        self.setFixedSize(360, 200)
        self.recorded_hotkey = ''
        self._recording = False
        self._pressed_modifiers = set()  # 当前按下的修饰键
        self._pressed_key = ''           # 当前按下的普通键

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 提示
        self.infoLabel = BodyLabel(f"当前快捷键: {current_hotkey.upper()}", self)
        layout.addWidget(self.infoLabel, alignment=Qt.AlignCenter)

        # 录制状态显示
        self.recordLabel = SubtitleLabel("点击下方按钮后按下新快捷键", self)
        self.recordLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.recordLabel)

        # 开始录制按钮
        self.recordBtn = PrimaryPushButton("开始录制", self)
        self.recordBtn.clicked.connect(self.start_recording)
        layout.addWidget(self.recordBtn)

        # 确认/取消按钮
        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(self.buttonBox)

    def start_recording(self):
        """进入录制模式，后续按键将被捕获"""
        self._recording = True
        self._pressed_modifiers.clear()
        self._pressed_key = ''
        self.recordBtn.setEnabled(False)
        self.recordLabel.setText("请按下快捷键组合...")
        # 确保对话框获取键盘焦点
        self.setFocus()
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if not self._recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # 如果按下的是修饰键，加入集合
        if key in self._MOD_MAP:
            self._pressed_modifiers.add(self._MOD_MAP[key])
            self._update_display()
            return

        # 忽略单独的 Escape（让用户可以取消）
        if key == Qt.Key_Escape and not self._pressed_modifiers:
            self._stop_recording()
            super().keyPressEvent(event)
            return

        # 普通键 — 与当前修饰键组合成完整快捷键
        key_name = self._qt_key_to_name(key)
        if key_name:
            self._pressed_key = key_name
            self._finalize_hotkey()

    def keyReleaseEvent(self, event):
        if not self._recording:
            super().keyReleaseEvent(event)
            return

        key = event.key()
        # 修饰键释放时从集合中移除
        if key in self._MOD_MAP:
            self._pressed_modifiers.discard(self._MOD_MAP[key])
            self._update_display()

    def _update_display(self):
        """实时显示当前按住的修饰键"""
        if self._pressed_modifiers:
            parts = sorted(self._pressed_modifiers)
            self.recordLabel.setText(f"当前按住: {'+'.join(p.upper() for p in parts)} + ...")
        else:
            self.recordLabel.setText("请按下快捷键组合...")

    def _finalize_hotkey(self):
        """组合键已完成，生成热键字符串"""
        # 构建 keyboard 库格式的热键字符串，如 'ctrl+shift+v'
        parts = sorted(self._pressed_modifiers) + [self._pressed_key]
        hotkey = '+'.join(parts)
        self.recorded_hotkey = hotkey

        self._stop_recording()
        self.recordLabel.setText(f"已录制: {hotkey.upper()}")
        self.recordBtn.setText("重新录制")
        self.recordBtn.setEnabled(True)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(True)

    def _stop_recording(self):
        """退出录制模式"""
        self._recording = False
        self._pressed_modifiers.clear()
        self._pressed_key = ''
        self.releaseKeyboard()
        self.recordBtn.setEnabled(True)

    @staticmethod
    def _qt_key_to_name(key):
        """将 Qt Key 枚举转换为 keyboard 库可识别的名称"""
        # 常见按键映射
        special = {
            Qt.Key_Space: 'space',
            Qt.Key_Return: 'enter',
            Qt.Key_Enter: 'enter',
            Qt.Key_Tab: 'tab',
            Qt.Key_Backspace: 'backspace',
            Qt.Key_Delete: 'delete',
            Qt.Key_Insert: 'insert',
            Qt.Key_Home: 'home',
            Qt.Key_End: 'end',
            Qt.Key_PageUp: 'page up',
            Qt.Key_PageDown: 'page down',
            Qt.Key_Up: 'up',
            Qt.Key_Down: 'down',
            Qt.Key_Left: 'left',
            Qt.Key_Right: 'right',
            Qt.Key_Escape: 'esc',
            Qt.Key_CapsLock: 'caps lock',
            Qt.Key_Print: 'print screen',
            Qt.Key_ScrollLock: 'scroll lock',
            Qt.Key_Pause: 'pause',
        }
        if key in special:
            return special[key]

        # F1-F12
        if Qt.Key_F1 <= key <= Qt.Key_F12:
            return f'f{key - Qt.Key_F1 + 1}'

        # 0-9
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)

        # A-Z
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key).lower()

        # 常见符号
        symbols = {
            Qt.Key_Minus: '-',
            Qt.Key_Equal: '=',
            Qt.Key_BracketLeft: '[',
            Qt.Key_BracketRight: ']',
            Qt.Key_Backslash: '\\',
            Qt.Key_Semicolon: ';',
            Qt.Key_Apostrophe: "'",
            Qt.Key_Comma: ',',
            Qt.Key_Period: '.',
            Qt.Key_Slash: '/',
            Qt.Key_QuoteLeft: '`',
        }
        if key in symbols:
            return symbols[key]

        return None

    def get_hotkey(self):
        return self.recorded_hotkey


class CustomRangeSettingCard(SettingCard):
    """自定义带滑块的设置卡片"""
    valueChanged = Signal(int)
    
    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        
        # 这里的布局直接添加到 self.hBoxLayout
        self.valLabel = QLabel("10", self)
        self.slider = Slider(Qt.Horizontal, self)
        
        # 设置固定宽度防止布局挤压
        self.slider.setFixedWidth(150)
        
        # 将组件添加到 SettingCard 默认的水平布局中
        self.hBoxLayout.addWidget(self.valLabel, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        
        self.slider.valueChanged.connect(self.__onValueChanged)
        
    def setRange(self, min_val, max_val):
        self.slider.setRange(min_val, max_val)
        
    def setValue(self, value):
        self.slider.setValue(value)
        self.valLabel.setText(str(value))
        
    def getValue(self):
        return self.slider.value()
        
    def __onValueChanged(self, value):
        self.valLabel.setText(str(value))
        self.valueChanged.emit(value)


class SettingsInterface(QWidget):
    """设置界面"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        
        # 1. 基础布局
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        
        # 2. 滚动区域设置 (关键：设置背景透明属性，防止绘图冲突)
        self.scrollArea = ScrollArea(self)
        self.scrollArea.setObjectName("settingsScrollArea")
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setStyleSheet("background-color: transparent; border: none;")
        self.scrollArea.viewport().setStyleSheet("background-color: transparent;")
        
        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName("scrollWidget")
        self.scrollWidget.setStyleSheet("background-color: transparent;")
        
        self.scrollArea.setWidget(self.scrollWidget)
        self.mainLayout.addWidget(self.scrollArea)
        
        # 3. 内容布局
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.expandLayout.setContentsMargins(30, 20, 30, 20)
        self.expandLayout.setSpacing(15)
        
        # 加载配置
        self.settings = load_settings()
        
        # --- 系统设置组 ---
        self.systemGroup = SettingCardGroup(self.tr("系统"), self.scrollWidget)
        
        self.startupCard = SwitchSettingCard(
            icon=FIF.POWER_BUTTON,
            title=self.tr("开机自启"),
            content=self.tr("在系统启动时自动运行"),
            parent=self.systemGroup
        )
        
        # 检查开机自启状态，并验证路径是否有效
        is_in_startup = startup.is_in_startup()
        if is_in_startup and not startup.is_startup_path_valid():
            # 路径无效，自动修复（使用当前exe的正确路径更新注册表）
            print(f"[Startup] 检测到注册表中的启动路径无效，正在自动修复...")
            print(f"[Startup] 旧路径: {startup.get_current_startup_path()}")
            startup.add_to_startup()  # 用当前正确的路径重新注册
            print(f"[Startup] 新路径: {startup.get_current_startup_path()}")
        
        self.startupCard.switchButton.setChecked(is_in_startup)
        self.startupCard.switchButton.checkedChanged.connect(self.on_startup_toggled)
        self.systemGroup.addSettingCard(self.startupCard)
        
        # 热键设置卡片
        current_hotkey = self.settings.get('hotkey', DEFAULT_HOTKEY)
        self.hotkeyCard = PushSettingCard(
            self.tr("更改"),
            icon=FIF.COMMAND_PROMPT,
            title=self.tr("全局快捷键"),
            content=self.tr(f"当前快捷键: {current_hotkey.upper()}"),
            parent=self.systemGroup
        )
        self.hotkeyCard.clicked.connect(self.on_hotkey_clicked)
        self.systemGroup.addSettingCard(self.hotkeyCard)
        
        self.expandLayout.addWidget(self.systemGroup)

        # --- 存储管理组 ---
        self.cleanGroup = SettingCardGroup(self.tr("存储管理"), self.scrollWidget)
        
        # 自动清理开关
        self.autoCleanCard = SwitchSettingCard(
            icon=FIF.DELETE,
            title=self.tr("自动清理"),
            content=self.tr("开启后自动清理旧记录"),
            parent=self.cleanGroup
        )
        self.autoCleanCard.switchButton.setChecked(self.settings.get('auto_clean_enabled', False))
        self.autoCleanCard.switchButton.checkedChanged.connect(self.on_clean_toggled)
        self.cleanGroup.addSettingCard(self.autoCleanCard)
        
        # 保留天数设置 (修复了之前的 Attribute Error)
        self.daysCard = CustomRangeSettingCard(
            icon=FIF.DATE_TIME,
            title=self.tr("保留天数"),
            content=self.tr("自动删除超过此天数的记录"),
            parent=self.cleanGroup
        )
        self.daysCard.setRange(1, 30)
        self.daysCard.setValue(self.settings.get('auto_clean_days', 10))
        self.daysCard.valueChanged.connect(self.on_days_changed)
        self.cleanGroup.addSettingCard(self.daysCard)
        
        # 手动清理按钮 (关键：使用 keyword 参数防止参数错位导致 QIcon 报错)
        self.manualCleanCard = PushSettingCard(
             text=self.tr("立即清理"),
             icon=FIF.BROOM,
             title=self.tr("手动清理"),
             content=self.tr("清理10日之前的所有记录"),
             parent=self.cleanGroup
        )
        self.manualCleanCard.clicked.connect(self.show_manual_clean_dialog)
        self.cleanGroup.addSettingCard(self.manualCleanCard)

        self.expandLayout.addWidget(self.cleanGroup)
        self.expandLayout.addStretch(1)

    def on_startup_toggled(self, checked):
        if checked:
            success = startup.add_to_startup()
            if success:
                InfoBar.success(
                    title="开机自启",
                    content=f"已启用开机自启",
                    orient=Qt.Horizontal,
                    parent=self
                )
            else:
                InfoBar.error(
                    title="开机自启",
                    content="启用失败，请检查权限",
                    orient=Qt.Horizontal,
                    parent=self
                )
                # 恢复开关状态
                self.startupCard.switchButton.setChecked(False)
        else:
            success = startup.remove_from_startup()
            if success:
                InfoBar.success(
                    title="开机自启",
                    content="已禁用开机自启",
                    orient=Qt.Horizontal,
                    parent=self
                )

    def on_clean_toggled(self, checked):
        self.settings['auto_clean_enabled'] = checked
        save_settings(self.settings)

    def on_days_changed(self, value):
        self.settings['auto_clean_days'] = value
        save_settings(self.settings)
        
    def show_manual_clean_dialog(self):
        try:
             # 获取天数，现在 daysCard 肯定存在了
             days = self.daysCard.getValue()
             date_str = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
             
             # 这里假设 database 模块有这个函数，如果没有请确保 database.py 中已定义
             if hasattr(database, 'delete_entries_before_date'):
                 count = database.delete_entries_before_date(date_str)
                 InfoBar.success(f"清理完成", f"已清理 {date_str} 之前的 {count} 条记录。", parent=self)
             else:
                 InfoBar.warning("未实现", "数据库模块缺少清理函数。", parent=self)
             
             # 刷新界面
             if self.window().clipboardInterface:
                 self.window().clipboardInterface.load_history()
                 
        except Exception as e:
             InfoBar.error("清理失败", str(e), parent=self)
    
    def on_hotkey_clicked(self):
        """热键设置按钮点击 — 打开快捷键录制对话框"""
        current_hotkey = self.settings.get('hotkey', DEFAULT_HOTKEY)
        
        # 录制前先临时移除当前热键，避免冲突
        main_window = self.window()
        if hasattr(main_window, '_hotkey_handle') and main_window._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(main_window._hotkey_handle)
                main_window._hotkey_handle = None
            except:
                pass
        
        try:
            dialog = HotkeyRecordDialog(current_hotkey, self)
            result = dialog.exec()
            
            if result == QDialog.Accepted and dialog.get_hotkey():
                new_hotkey = dialog.get_hotkey()
                self.settings['hotkey'] = new_hotkey
                save_settings(self.settings)
                
                # 更新卡片显示文本
                self.hotkeyCard.setContent(f"当前快捷键: {new_hotkey.upper()}")
                
                InfoBar.success(
                    title="快捷键已更新",
                    content=f"新快捷键: {new_hotkey.upper()}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=2000,
                    parent=self
                )
        finally:
            # 无论成功、取消、还是异常，都重新注册热键
            if hasattr(main_window, 'setup_hotkey'):
                main_window.setup_hotkey()

class MainWindow(MSFluentWindow):
    # 定义信号用于跨线程安全地切换窗口
    toggleWindowSignal = Signal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("clip Book")
        
        # 设置窗口图标
        icon_path = resource_path('icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            self.setWindowIcon(FIF.PASTE.icon())
            
        self.titleBar.titleLabel.show() # Make sure it's visible
        self.resize(300, 500)
        
        self.hotkey_id = 1  # 唯一 ID
        # 居中显示
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)

        # 创建子界面
        self.clipboardInterface = ClipboardInterface(self)
        self.settingsInterface = SettingsInterface(self)
        
        # 初始化导航栏
        self.initNavigation()
        self.initTitleBar()
        
        # 隐藏导航栏分割线
        self.hide_navigation_separator()
        
        # 启动监听和加载数据
        self.clipboardInterface.load_history()
        self.start_monitor_thread()
        self.create_tray_icon()
        
        # 设置全局热键
        self.setup_hotkey()
        
        # 连接信号
        self.toggleWindowSignal.connect(self.toggle_window)
        
        # 启用毛玻璃效果 - 暂时禁用，因为会导致颜色异常
        # self.enable_acrylic_effect()
    
    def hide_navigation_separator(self):
        """隐藏导航栏和内容区域之间的分割线，并设置半透明背景"""
        from PySide6.QtGui import QPainter, QColor, QPalette
        
        # 1. 定义统一的背景色
        bg_color = "#F5F5F5"  # 浅灰色
        q_color = QColor(bg_color)
        
        # 2. 设置主窗口背景色
        self.setBackgroundColor(q_color)
        
        
        # 3. 强制设置导航栏背景色（使用多种方法确保生效）
        # 方法1: QPalette
        nav_palette = self.navigationInterface.palette()
        nav_palette.setColor(QPalette.Window, q_color)
        nav_palette.setColor(QPalette.Base, q_color)
        nav_palette.setColor(QPalette.Button, q_color)
        self.navigationInterface.setPalette(nav_palette)
        self.navigationInterface.setAutoFillBackground(True)
        
        
        # 方法2: QSS - 强制所有子元素都使用相同背景色
        self.navigationInterface.setStyleSheet(f"""
            NavigationInterface,
            NavigationInterface QWidget,
            NavigationInterface QScrollArea,
            NavigationInterface QFrame,
            NavigationInterface #view {{
                background-color: {bg_color} !important;
                border: none;
            }}
            NavigationPushButton {{
                background-color: transparent;
                border: none;
            }}
            NavigationPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.05);
            }}
            NavigationPushButton:checked {{
                background-color: rgba(0, 120, 212, 0.1);
            }}
        """)
        
        # 方法3: 遍历所有子控件，强制设置背景色
        def set_widget_background(widget, color):
            """递归设置所有子控件的背景色"""
            palette = widget.palette()
            palette.setColor(QPalette.Window, color)
            palette.setColor(QPalette.Base, color)
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
            for child in widget.findChildren(QWidget):
                if 'Button' not in child.__class__.__name__:  # 不影响按钮
                    child_palette = child.palette()
                    child_palette.setColor(QPalette.Window, color)
                    child_palette.setColor(QPalette.Base, color)
                    child.setPalette(child_palette)
                    child.setAutoFillBackground(True)
        
        set_widget_background(self.navigationInterface, q_color)
        
        # 4. 设置 StackedWidget（内容区）背景色
        if hasattr(self, 'stackedWidget'):
            self.stackedWidget.setStyleSheet(f"""
                QStackedWidget {{
                    background-color: {bg_color};
                    border: none;
                }}
            """)
            
        # 5. 标题栏背景色
        self.titleBar.setStyleSheet(f"""
            TitleBar {{
                background-color: {bg_color};
                border: none;
            }}
            QLabel {{
                color: #4A4543;
                background-color: transparent;
            }}
        """)
        
        # 6. 隐藏分割线
        children = self.findChildren(QFrame)
        for child in children:
            if child.frameShape() == QFrame.VLine:
                child.hide()
                
        # 7. 强制刷新
        self.navigationInterface.update()
        
    def paintEvent(self, event):
        """重写主窗口 paintEvent - 保持透明以支持 Acrylic 效果"""
        # 不绘制任何背景，让 Windows 11 Acrylic 材质接管
        # 如果绘制了纯色背景，Acrylic 效果将不会生效
        super().paintEvent(event)
    
    def enable_acrylic_effect(self):
        """启用 Windows 11 Acrylic 毛玻璃效果"""
        try:
            import ctypes
            from ctypes import wintypes, c_int, Structure, byref
            
            # 获取窗口句柄
            hwnd = int(self.winId())
            dwmapi = ctypes.windll.dwmapi
            
            # 关键：设置窗口背景为透明，这样 Acrylic 材质才能生效
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            
            # Windows 11 Acrylic 效果
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            # 2 = None, 3 = Mica, 4 = Acrylic
            DWMSBT_ACRYLIC = c_int(4)
            
            result = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_SYSTEMBACKDROP_TYPE,
                byref(DWMSBT_ACRYLIC),
                ctypes.sizeof(DWMSBT_ACRYLIC)
            )
            
            if result == 0:
                print("[Acrylic] Windows 11 Acrylic 材质已启用")
            else:
                print(f"[Acrylic] DwmSetWindowAttribute 返回错误码: {result}")
                # 如果失败，尝试使用传统方法
                self.enable_legacy_blur()
            
        except Exception as e:
            print(f"[Acrylic] 启用失败: {e}")
            
    def enable_legacy_blur(self):
        """备用方案：Windows 10 的传统模糊效果"""
        try:
            import ctypes
            from ctypes import wintypes, Structure, byref
            
            hwnd = int(self.winId())
            
            class DWM_BLURBEHIND(Structure):
                _fields_ = [
                    ("dwFlags", wintypes.DWORD),
                    ("fEnable", wintypes.BOOL),
                    ("hRgnBlur", wintypes.HANDLE),
                    ("fTransitionOnMaximized", wintypes.BOOL)
                ]
            
            DWM_BB_ENABLE = 0x00000001
            
            blur_behind = DWM_BLURBEHIND()
            blur_behind.dwFlags = DWM_BB_ENABLE
            blur_behind.fEnable = True
            blur_behind.hRgnBlur = None
            blur_behind.fTransitionOnMaximized = False
            
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmEnableBlurBehindWindow(hwnd, byref(blur_behind))
            
            print("[Acrylic] 已启用传统 DWM 模糊效果")
        except Exception as e:
            print(f"[Acrylic] 传统模糊启用失败: {e}")

    def initTitleBar(self):
        # 简化标题栏，移除搜索框
        self.titleBar.titleLabel.setStyleSheet("""
            QLabel {
                background: transparent;
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 15px;
                font-weight: bold;
                padding-left: 10px;
            }
        """)


    def initNavigation(self):
        self.addSubInterface(self.clipboardInterface, FIF.PASTE, "剪贴板")
        
        # 关键修改：加上 position= 关键字参数
        self.addSubInterface(
            self.settingsInterface, 
            FIF.SETTING, 
            "设置", 
            position=NavigationItemPosition.BOTTOM
        )

    def start_monitor_thread(self):
        self.monitor_thread = QThread()
        self.clipboard_monitor = ClipboardMonitor()
        self.clipboard_monitor.moveToThread(self.monitor_thread)
        # 增量更新：仅插入新卡片，不重建整个列表
        self.clipboard_monitor.newEntryDetected.connect(self.clipboardInterface.on_new_entry)
        # 全量刷新：仅在合并重复时触发
        self.clipboard_monitor.fullRefreshNeeded.connect(self.clipboardInterface.load_history)
        self.monitor_thread.started.connect(self.clipboard_monitor.run)
        self.monitor_thread.start()

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path('icon.ico')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(FIF.PASTE.icon()) # Fallback
            
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        menu = QMenu(self)
        action_show = QAction(FIF.VIEW.icon(), "显示", self)
        action_show.triggered.connect(self.show)
        action_quit = QAction(FIF.CLOSE.icon(), "退出", self)
        action_quit.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(action_show)
        menu.addAction(action_quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()

    def setup_hotkey(self):
        """设置全局热键（使用 Windows Native API）"""
        user32 = ctypes.windll.user32
        
        # 1. 先注销旧热键
        try:
            user32.UnregisterHotKey(int(self.winId()), self.hotkey_id)
        except Exception:
            pass
            
        # 2. 读取配置并解析
        settings = load_settings()
        hotkey_str = settings.get('hotkey', DEFAULT_HOTKEY)
        
        modifiers, vk_code = parse_hotkey(hotkey_str)
        
        if vk_code == 0:
            print(f"[Hotkey] 解析失败或快捷键无效: {hotkey_str}")
            return

        # 3. 注册新热键
        # RegisterHotKey(hWnd, id, fsModifiers, vk)
        try:
            result = user32.RegisterHotKey(
                int(self.winId()),
                self.hotkey_id,
                modifiers,
                vk_code
            )
            
            if result:
                print(f"[Hotkey] 已注册全局热键 (Native): {hotkey_str.upper()}")
            else:
                print(f"[Hotkey] 注册热键失败 (Native). Error: {ctypes.GetLastError()}")
                InfoBar.error(
                    title='热键冲突',
                    content=f'无法注册快捷键 {hotkey_str.upper()}，可能已被占用。',
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
        except Exception as e:
            print(f"[Hotkey] 注册异常: {e}")

    def nativeEvent(self, eventType, message):
        """处理 Windows 原生消息，拦截 WM_HOTKEY"""
        try:
            if eventType == b"windows_generic_MSG":
                 msg = ctypes.wintypes.MSG.from_address(int(message))
                 if msg.message == win32con.WM_HOTKEY:
                     if msg.wParam == self.hotkey_id:
                         self.toggleWindowSignal.emit()
                         return True, 0
            # For older PySide6 or different event types, sometimes just try/except is safer
        except Exception as e:
            # print(f"[NativeEvent] Error: {e}")
            pass
            
        return super().nativeEvent(eventType, message)
    
    def _on_hotkey_pressed(self):
        # Deprecated: keyboard library callback
        pass
    
    def toggle_window(self):
        """切换窗口显示/隐藏状态"""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show()
            self.showNormal()  # 如果是最小化状态，恢复正常
            self.activateWindow()
            self.raise_()  # 确保窗口在最前面
    
    def closeEvent(self, event):
        # 退出前注销热键
        user32 = ctypes.windll.user32
        try:
            user32.UnregisterHotKey(int(self.winId()), self.hotkey_id)
        except:
            pass
        event.ignore()
        self.hide()

if __name__ == '__main__':
    database.init_db()
    
    # 启用高DPI缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 设置莫兰迪色调主题
    setTheme(Theme.LIGHT)  # 使用亮色主题
    setThemeColor("#9B8578")  # 莫兰迪棕色作为主题色
    
    # 应用自定义样式表（主要用于调整背景和边框等细节）
    app.setStyleSheet(MODERN_STYLESHEET)
    
    w = MainWindow()
    # 显式切换到第一个界面，避免启动时的空白或同步问题
    w.navigationInterface.setCurrentItem(w.clipboardInterface.objectName())
    w.show()
    
    sys.exit(app.exec())
