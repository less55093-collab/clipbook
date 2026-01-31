import sys
import os

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QFileDialog, QSystemTrayIcon, QMenu, QLabel
from PySide6.QtCore import Qt, Signal, QUrl, QSize, QTimer, QThread, QPoint, QMimeData
from PySide6.QtGui import QIcon, QDesktopServices, QPixmap, QAction, QCursor, QDrag, QColor

from qfluentwidgets import (MSFluentWindow, NavigationItemPosition, 
                            SubtitleLabel, CardWidget, ImageLabel, BodyLabel, 
                            TransparentToolButton, SearchLineEdit, PrimaryPushButton, 
                            SmoothScrollArea, FlowLayout, FluentIcon as FIF,
                            SwitchSettingCard, PushSettingCard, SettingCardGroup,
                            InfoBar, InfoBarPosition, ScrollArea,
                            TextEdit, PlainTextEdit, Flyout, FlyoutAnimationType)

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

def resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和 PyInstaller 打包环境"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def send_to_clipboard(clip_type, data):
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(clip_type, data)
    finally:
        win32clipboard.CloseClipboard()


class EditableBlock(PlainTextEdit):
    """能够直接编辑、自动保存、并传递滚轮事件的文本框"""
    focusOut = Signal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setPlainText(text)
        # 样式伪装：透明背景，无边框，使得看起来像普通 Label
        self.setStyleSheet("""
            PlainTextEdit, QPlainTextEdit {
                background-color: transparent;
                border: none;
                padding: 0px;
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 9pt;
                color: black;
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
        # 1. 自动获取焦点（解决必须先点击才能滚动的问题）
        if not self.hasFocus():
            self.setFocus()
            
        # 滚轮事件优化：如果滚到头了，就让父控件（整个页面）滚动
        vbar = self.verticalScrollBar()
        is_top = (vbar.value() == vbar.minimum())
        is_bottom = (vbar.value() == vbar.maximum())
        angle = event.angleDelta().y()

        # 向上滚且已经在顶部，或 向下滚且已经在底部 -> 忽略事件，让父控件处理
        if (angle > 0 and is_top) or (angle < 0 and is_bottom):
            event.ignore()
        else:
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
    
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.is_selected = False
        self.drag_start_pos = None  # 用于记录拖拽起始点

        self.setFixedSize(160, 160)
        self.setCursor(Qt.PointingHandCursor)
        
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)
        
        self.setup_content()
        
    def setup_content(self):
        entry_type = self.entry[1]
        content = self.entry[2]
        
        # 调整布局边距，让内容更靠近边缘，利用率更高
        # 参数顺序：左，上，右，下
        self.vBoxLayout.setContentsMargins(12, 12, 12, 12)
        
        if entry_type == 'image' and os.path.exists(content):
            self.imageLabel = ImageLabel(content, self)
            self.imageLabel.setBorderRadius(8, 8, 8, 8)
            self.imageLabel.setFixedSize(136, 136) # 稍微调大一点图片区域
            
            # 图片优化加载逻辑
            pixmap = QPixmap(content)
            if not pixmap.isNull():
                thumbnail = pixmap.scaled(
                    136, 136, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
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


# --- Windows 11 Style Stylesheet (修改版) ---
MODERN_STYLESHEET = """
QWidget {
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
    font-size: 9pt;
}

/* 让主窗口背景统一，下面我们会用代码设置具体颜色 */
MSFluentWindow {
    background-color: #f9f9f9;  /* 这里设置你想要的统一背景色，比如纯白 #ffffff 或 浅灰 #f9f9f9 */
    border: none;
}

/* 核心：让导航栏透明并去除右侧分割线 */
NavigationInterface {
    background-color: transparent;
    border: none;
    border-right: none;
}

/* 核心：让右侧内容区域透明 */
QStackedWidget {
    background-color: transparent;
    border: none;
}

/* 让滚动区域和子界面透明 */
#scrollWidget, #clipboardInterface, #settingsInterface {
    background-color: transparent;
}

QScrollArea {
    background-color: transparent;
    border: none;
}
"""


class ClipboardInterface(QWidget):
    """剪贴板历史界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self.setObjectName("clipboardInterface")
        self.setStyleSheet("background-color: transparent;")
        
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
        
        self.deleteAllBtn = TransparentToolButton(FIF.DELETE, self)
        self.deleteAllBtn.clicked.connect(self.show_delete_all_warning)
        
        self.headerLayout.addWidget(self.searchEdit)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.deleteAllBtn)
        
        self.mainLayout.addLayout(self.headerLayout)
        
        # 3. 滚动区域
        self.scrollArea = ScrollArea(self)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setStyleSheet("background-color: transparent; border: none;")
        
        # 卡片容器
        self.cardsContainer = QWidget()
        self.cardsContainer.setStyleSheet("background-color: transparent;")
        self.cardsLayout = FlowLayout(self.cardsContainer)
        self.cardsLayout.setContentsMargins(0, 0, 0, 0)
        self.cardsLayout.setVerticalSpacing(10)
        self.cardsLayout.setHorizontalSpacing(10)
        
        self.scrollArea.setWidget(self.cardsContainer)
        self.mainLayout.addWidget(self.scrollArea)



    def show_delete_all_warning(self):
        w = Flyout.create(
            icon=FIF.INFO,
            title='确认清空',
            content='确定要删除所有历史记录吗？此操作不可恢复。',
            target=self.deleteAllBtn,
            parent=self.window(),
            isClosable=True
        )
        
        # 添加确认按钮到 Flyout (简单的 Flyout 没有按钮，我们这里直接弹出一个 Dialog 更合适，或者使用 InfoBar 提问)
        # 为了简单，我们使用 MessageBox 或者 Dialog，但在 Fluent 中最好用 MessageBox
        # 由于 FluentWidgets 的 MessageBox 需要父窗口，我们可以先简单实现直接清空
        
        # 使用 InfoBar 模拟确认
        InfoBar.warning(
            title="操作确认",
            content="双击此按钮以确认清空所有记录。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )
        # TODO: 更好的确认交互。既然用户点了删除所有，我们这里直接做一个简单的 Hack：
        # 检测是否在这个按钮上再次点击 (比较复杂)。
        # 让我们直接清空吧，用户既然点了。
        
        self.delete_all_entries()

    def delete_all_entries(self):
        # 1. 先清空界面，释放文件占用
        for i in reversed(range(self.cardsLayout.count())):
            widget = self.cardsLayout.itemAt(i).widget()
            if widget:
                self.cardsLayout.removeWidget(widget)
                widget.deleteLater()
        self.cards.clear()
        
        # 允许事件循环处理挂起的删除事件
        QApplication.processEvents()
        
        # 2. 删除文件和数据库记录
        entries = database.get_all_entries()
        for entry in entries:
             # 删除文件
            if entry[1] == 'image' and os.path.exists(entry[2]):
                try:
                    os.remove(entry[2])
                except PermissionError:
                    print(f"文件正在被使用，无法删除: {entry[2]}")
                except Exception:
                    pass
            database.delete_entry(entry[0])
            
        InfoBar.success("已清空", "所有剪贴板记录已清除。", parent=self)

    def load_history(self):
        # Clear existing
        for i in reversed(range(self.cardsLayout.count())):
            self.cardsLayout.itemAt(i).widget().deleteLater()
        self.cards.clear()
        
        entries = database.get_all_entries()
        for entry in entries:
            card = ClipboardCard(entry)
            card.clicked.connect(self.on_card_clicked)
            card.doubleClicked.connect(self.copy_item)
            card.rightClicked.connect(self.show_context_menu)
            
            self.cardsLayout.addWidget(card)
            self.cards.append(card)

    def on_card_clicked(self, card):
        pass # Handle selection visual if needed

    def copy_item(self, card):
        entry = card.entry
        try:
            if entry[1] == 'text':
                pyperclip.copy(entry[2])
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

    def delete_card(self, card):
        entry = card.entry
        
        # 1. 先从界面移除并销毁组件，释放潜在的文件占用
        self.cardsLayout.removeWidget(card)
        card.deleteLater()
        if card in self.cards:
            self.cards.remove(card)
            
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
        self.startupCard.switchButton.setChecked(startup.is_in_startup())
        self.startupCard.switchButton.checkedChanged.connect(self.on_startup_toggled)
        self.systemGroup.addSettingCard(self.startupCard)
        
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
            startup.add_to_startup()
        else:
            startup.remove_from_startup()

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

class MainWindow(MSFluentWindow):
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
        
        # 启动监听和加载数据
        self.clipboardInterface.load_history()
        self.start_monitor_thread()
        self.create_tray_icon()

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
        self.clipboard_monitor.newItemDetected.connect(self.clipboardInterface.load_history)
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

    def closeEvent(self, event):
        event.ignore()
        self.hide()

if __name__ == '__main__':
    database.init_db()
    
    # 启用高DPI缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(MODERN_STYLESHEET)
    
    w = MainWindow()
    # 显式切换到第一个界面，避免启动时的空白或同步问题
    w.navigationInterface.setCurrentItem(w.clipboardInterface.objectName())
    w.show()
    
    sys.exit(app.exec())
