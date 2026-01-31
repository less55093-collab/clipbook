"""
图片编辑器模块 - 提供简单的图片标注功能
"""
import os
import math
from io import BytesIO
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QSlider, QColorDialog, QToolButton,
                               QButtonGroup, QWidget, QToolTip)
from PySide6.QtGui import (QPixmap, QPainter, QPen, QColor, QCursor, QImage,
                           QPolygonF, QBrush)
from PySide6.QtCore import Qt, QPoint, QPointF, Signal
from PIL import Image
import win32clipboard
import win32con


class DrawingCanvas(QLabel):
    """可绘制的画布"""
    
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.drawing_pixmap = pixmap.copy()
        self.setPixmap(self.drawing_pixmap)
        self.setMouseTracking(True)
        
        # 绘制状态
        self.drawing = False
        self.last_point = None
        self.current_tool = 'pen'  # 'pen' or 'arrow'
        self.pen_color = QColor('#FF0000')
        self.pen_width = 3
        
        # 历史记录用于撤销/重做
        self.history = [pixmap.copy()]
        self.history_index = 0
        
        # 箭头绘制临时状态
        self.arrow_start = None
        self.temp_pixmap = None
        
    def set_tool(self, tool):
        self.current_tool = tool
        
    def set_color(self, color):
        self.pen_color = color
        
    def set_width(self, width):
        self.pen_width = width
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.last_point = event.pos()
            
            if self.current_tool == 'arrow':
                self.arrow_start = event.pos()
                self.temp_pixmap = self.drawing_pixmap.copy()
                
    def mouseMoveEvent(self, event):
        if not self.drawing:
            return
            
        if self.current_tool == 'pen':
            painter = QPainter(self.drawing_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(self.last_point, event.pos())
            painter.end()
            self.last_point = event.pos()
            self.setPixmap(self.drawing_pixmap)
            
        elif self.current_tool == 'arrow' and self.arrow_start:
            # 实时预览箭头
            preview = self.temp_pixmap.copy()
            self.draw_arrow(preview, self.arrow_start, event.pos())
            self.setPixmap(preview)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            
            if self.current_tool == 'arrow' and self.arrow_start:
                # 确定绘制箭头
                self.draw_arrow(self.drawing_pixmap, self.arrow_start, event.pos())
                self.setPixmap(self.drawing_pixmap)
                self.arrow_start = None
                self.temp_pixmap = None
            
            # 保存历史记录
            self.save_history()
            
    def draw_arrow(self, pixmap, start, end):
        """绘制箭头"""
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.pen_color))
        
        # 计算箭头方向
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)
        
        if length < 5:
            painter.end()
            return
            
        # 单位向量
        ux = dx / length
        uy = dy / length
        
        # 箭头大小
        arrow_size = min(15, length * 0.3)
        
        # 箭头线段
        painter.drawLine(start, end)
        
        # 箭头头部
        angle = math.atan2(dy, dx)
        arrow_angle = math.pi / 6  # 30度
        
        p1 = QPointF(
            end.x() - arrow_size * math.cos(angle - arrow_angle),
            end.y() - arrow_size * math.sin(angle - arrow_angle)
        )
        p2 = QPointF(
            end.x() - arrow_size * math.cos(angle + arrow_angle),
            end.y() - arrow_size * math.sin(angle + arrow_angle)
        )
        
        arrow_head = QPolygonF([QPointF(end.x(), end.y()), p1, p2])
        painter.drawPolygon(arrow_head)
        painter.end()
        
    def save_history(self):
        """保存当前状态到历史记录"""
        # 删除当前位置之后的历史（用于重做时的分支）
        self.history = self.history[:self.history_index + 1]
        self.history.append(self.drawing_pixmap.copy())
        self.history_index = len(self.history) - 1
        
        # 限制历史记录数量
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_index -= 1
            
    def undo(self):
        """撤销"""
        if self.history_index > 0:
            self.history_index -= 1
            self.drawing_pixmap = self.history[self.history_index].copy()
            self.setPixmap(self.drawing_pixmap)
            
    def redo(self):
        """重做"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.drawing_pixmap = self.history[self.history_index].copy()
            self.setPixmap(self.drawing_pixmap)
            
    def get_result(self):
        """获取编辑结果"""
        return self.drawing_pixmap


class ImageEditorDialog(QDialog):
    """图片编辑对话框"""
    
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle("图片编辑")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        
        # 加载图片
        self.original_pixmap = QPixmap(image_path)
        
        # 限制显示尺寸
        screen_size = self.screen().availableGeometry()
        max_width = int(screen_size.width() * 0.8)
        max_height = int(screen_size.height() * 0.8)
        
        display_pixmap = self.original_pixmap
        if self.original_pixmap.width() > max_width or self.original_pixmap.height() > max_height:
            display_pixmap = self.original_pixmap.scaled(
                max_width, max_height, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
        
        self.setup_ui(display_pixmap)
        self.resize(display_pixmap.width() + 40, display_pixmap.height() + 100)
        
    def setup_ui(self, pixmap):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 工具按钮组
        self.tool_group = QButtonGroup(self)
        
        self.pen_btn = QToolButton()
        self.pen_btn.setText("✏️ 画笔")
        self.pen_btn.setCheckable(True)
        self.pen_btn.setChecked(True)
        self.pen_btn.setStyleSheet("QToolButton { padding: 8px 12px; }")
        self.tool_group.addButton(self.pen_btn, 0)
        
        self.arrow_btn = QToolButton()
        self.arrow_btn.setText("➡️ 箭头")
        self.arrow_btn.setCheckable(True)
        self.arrow_btn.setStyleSheet("QToolButton { padding: 8px 12px; }")
        self.tool_group.addButton(self.arrow_btn, 1)
        
        toolbar.addWidget(self.pen_btn)
        toolbar.addWidget(self.arrow_btn)
        
        # 分隔
        toolbar.addSpacing(20)
        
        # 颜色选择
        self.color_btn = QPushButton("🎨 颜色")
        self.color_btn.setStyleSheet("QPushButton { background-color: #FF0000; color: white; padding: 8px 12px; }")
        self.color_btn.clicked.connect(self.choose_color)
        toolbar.addWidget(self.color_btn)
        
        # 线宽
        toolbar.addWidget(QLabel("线宽:"))
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(1, 20)
        self.width_slider.setValue(3)
        self.width_slider.setFixedWidth(100)
        self.width_slider.valueChanged.connect(self.change_width)
        toolbar.addWidget(self.width_slider)
        
        # 分隔
        toolbar.addSpacing(20)
        
        # 撤销/重做
        self.undo_btn = QPushButton("↩️ 撤销")
        self.undo_btn.clicked.connect(self.undo)
        toolbar.addWidget(self.undo_btn)
        
        self.redo_btn = QPushButton("↪️ 重做")
        self.redo_btn.clicked.connect(self.redo)
        toolbar.addWidget(self.redo_btn)
        
        toolbar.addStretch()
        
        # 完成按钮
        self.done_btn = QPushButton("✅ 完成并复制")
        self.done_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 8px 16px; font-weight: bold; }")
        self.done_btn.clicked.connect(self.finish_editing)
        toolbar.addWidget(self.done_btn)
        
        layout.addLayout(toolbar)
        
        # 画布
        self.canvas = DrawingCanvas(pixmap, self)
        self.canvas.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.canvas)
        
        # 连接工具切换
        self.tool_group.idClicked.connect(self.change_tool)
        
    def change_tool(self, tool_id):
        if tool_id == 0:
            self.canvas.set_tool('pen')
        else:
            self.canvas.set_tool('arrow')
            
    def choose_color(self):
        color = QColorDialog.getColor(self.canvas.pen_color, self, "选择颜色")
        if color.isValid():
            self.canvas.set_color(color)
            self.color_btn.setStyleSheet(f"QPushButton {{ background-color: {color.name()}; color: white; padding: 8px 12px; }}")
            
    def change_width(self, value):
        self.canvas.set_width(value)
        
    def undo(self):
        self.canvas.undo()
        
    def redo(self):
        self.canvas.redo()
        
    def finish_editing(self):
        """完成编辑并复制到剪贴板"""
        result_pixmap = self.canvas.get_result()
        
        # 转换为PIL Image并复制到剪贴板
        image = result_pixmap.toImage()
        
        # 转换为bytes
        buffer = BytesIO()
        
        # QImage -> PIL Image
        width = image.width()
        height = image.height()
        
        # 确保格式正确
        image = image.convertToFormat(QImage.Format_RGBA8888)
        ptr = image.bits()
        
        pil_image = Image.frombytes('RGBA', (width, height), bytes(ptr))
        pil_image = pil_image.convert('RGB')
        
        # 保存为BMP格式
        output = BytesIO()
        pil_image.save(output, 'BMP')
        data = output.getvalue()[14:]  # 去掉BMP文件头
        output.close()
        
        # 复制到剪贴板
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)
            win32clipboard.CloseClipboard()
            
            QToolTip.showText(QCursor.pos(), "编辑后的图片已复制到剪贴板!", msecShowTime=2000)
        except Exception as e:
            QToolTip.showText(QCursor.pos(), f"复制失败: {e}", msecShowTime=2000)
            
        self.accept()
