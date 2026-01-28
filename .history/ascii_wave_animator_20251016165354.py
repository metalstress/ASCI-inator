# -*- coding: utf-8 -*-
"""
ASCII Wave Animator — Figma Design Edition
Полное повторение дизайна из Figma: минималистичный black&white интерфейс
"""
import sys, os, math, re, glob, random, json
from dataclasses import dataclass
import numpy as np
import time
# Предпочитаем scipy, но безопасно фоллбэкаемся, если её нет
try:
    from scipy.ndimage import gaussian_filter as _scipy_gaussian_filter
    SCIPY_AVAILABLE = True
except Exception:
    _scipy_gaussian_filter = None
    SCIPY_AVAILABLE = False
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QImage, QPixmap, QAction, QColor, QFont, QIcon, QPainter, QPen, QRadialGradient, QPainterPath, QRegion, QFontDatabase, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
    QSlider, QCheckBox, QGroupBox, QMessageBox, QLineEdit, QComboBox, QColorDialog,
    QTabWidget, QScrollArea, QGridLayout, QSizePolicy, QInputDialog, QDialog, QProgressBar,
    QGraphicsDropShadowEffect, QGraphicsBlurEffect, QGraphicsOpacityEffect, QStackedWidget,
    QDialogButtonBox, QSpacerItem
)

try:
    import sounddevice as sd
except Exception:
    sd = None

ASCII_RAMP_PURE = " .:-=+*#%@"
ASCII_RAMP_EXT = " .`^\",:;Il!i><~+_-?][}{1)(|/\\tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$█"

# DRY: use shared utils
from asciinator.utils.icons import load_icon

from asciinator.utils.image_ops import (
    clamp01,
    to_grayscale,
    resize_to_char_grid,
    build_ascii_image_color,
)

# core modules (restored)
from asciinator.core.waves import WaveParams, apply_waves_time

@dataclass
class WaveParams:
    freq_x: float = 0.8
    freq_y: float = 0.6
    speed_x: float = 1.2
    speed_y: float = -0.9
    amplitude: float = 0.25
    contrast: float = 1.0

def generate_random_shapes(width, height, n=30, angularity=0.5, seed=None):
    rng = np.random.default_rng(seed)
    img = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(img, 'L')
    for i in range(n):
        cx = rng.integers(0, width)
        cy = rng.integers(0, height)
        r = rng.integers(min(width, height)//20, min(width, height)//5)
        sides = int(3 + (1-angularity)*5 + angularity*20)
        pts = []
        for k in range(sides):
            a = 2*math.pi*k/sides + rng.random()*0.2*angularity
            rr = r*(0.7 + 0.6*rng.random()*angularity)
            pts.append((cx + rr*math.cos(a), cy + rr*math.sin(a)))
        fill = int(rng.integers(80, 240))
        d.polygon(pts, fill=fill)
    return np.array(img, dtype=np.float32)/255.0

# ==================== CUSTOM WIDGETS ====================

class RoundButton(QPushButton):
    # Круглая кнопка -/+ из дизайна
    def __init__(self, text, is_white_bg=False):
        super().__init__(text)
        self.is_white_bg = is_white_bg
        self.setFixedSize(44, 40)
        self.setCursor(Qt.PointingHandCursor)

class NumberDisplay(QLabel):
    # Большое число в дизайне (Bold 24px) - кликабельное для ввода
    clicked = Signal()
    
    def __init__(self, text="40"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(68, 44)
        self.setCursor(Qt.IBeamCursor)
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

class NewStepperWidget(QWidget):
    # Новый виджет: число + кнопки -/+ в стиле редизайна
    valueChanged = Signal(int)
    
    def __init__(self, value=40, minimum=8, maximum=400, parent=None, label_text=""):
        super().__init__()
        self._value = value
        self.minimum = minimum
        self.maximum = maximum
        self.parent_window = parent
        self.label_text = label_text
        
        # Адаптивная ширина: минимум для сохранения дизайна, растягивается по горизонтали
        self.setMinimumWidth(166)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)  # Небольшой отступ между числом и кнопками
        
        # Числовое поле (68x44px) - теперь редактируемое
        self.display = QLineEdit(str(value))
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setFixedHeight(44)
        self.display.setMinimumWidth(56)
        self.display.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.display.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: white;
                font-size: 24px;
                font-weight: bold;
                border: none;
                border-radius: 10px;
            }
            QLineEdit:focus {
                background: rgba(255,255,255,0.05);
            }
        """)
        
        # Валидация: только цифры
        self.display.setValidator(QIntValidator(self.minimum, self.maximum))
        
        # Обработчики редактирования
        self.display.editingFinished.connect(self._on_text_edited)
        self.display.returnPressed.connect(self._on_text_edited)
        
        # Контейнер для кнопок -/+ "таблетка" с общей обводкой
        buttons_container = QWidget()
        buttons_container.setFixedHeight(44)
        buttons_container.setMinimumWidth(76)
        buttons_container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        buttons_container.setStyleSheet("""
            QWidget {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
            }
        """)
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(2, 2, 2, 2)  # Компенсируем border
        buttons_layout.setSpacing(0)
        
        # Кнопка минус (44x40px, с учетом margins будет помещаться)
        self.btn_minus = QPushButton("-")
        self.btn_minus.setFixedHeight(40)
        self.btn_minus.setMinimumWidth(36)
        self.btn_minus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-size: 24px;
                font-weight: normal;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border-top-left-radius: 18px;
                border-bottom-left-radius: 18px;
            }
        """)
        
        # Кнопка плюс (44x40px, с учетом margins будет помещаться)
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedHeight(40)
        self.btn_plus.setMinimumWidth(36)
        self.btn_plus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-size: 24px;
                font-weight: normal;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border-top-right-radius: 18px;
                border-bottom-right-radius: 18px;
            }
        """)
        
        buttons_layout.addWidget(self.btn_minus)
        
        # Вертикальная линия-разделитель (короче на 8px сверху и снизу)
        separator_container = QWidget()
        separator_container.setFixedSize(1, 40)  # Высота = высота кнопок
        separator_container.setStyleSheet("background: transparent;")
        separator_layout = QVBoxLayout(separator_container)
        separator_layout.setContentsMargins(0, 4, 0, 4)
        separator_layout.setSpacing(0)
        
        separator_line = QWidget()
        separator_line.setStyleSheet("background: white;")
        separator_layout.addWidget(separator_line)
        
        buttons_layout.addWidget(separator_container)
        buttons_layout.addWidget(self.btn_plus)
        
        layout.addWidget(self.display, 1)
        layout.addWidget(buttons_container, 0)
        
        self.btn_minus.clicked.connect(self.decrease)
        self.btn_plus.clicked.connect(self.increase)
        
    def decrease(self):
        if self._value > self.minimum:
            self._value -= 1
            self.display.setText(str(self._value))
            self.valueChanged.emit(self._value)
    
    def increase(self):
        if self._value < self.maximum:
            self._value += 1
            self.display.setText(str(self._value))
            self.valueChanged.emit(self._value)
    
    def _on_text_edited(self):
        """Обработчик ручного ввода значения"""
        text = self.display.text().strip()
        if text:
            try:
                new_value = int(text)
                # Клампим значение в пределах min-max
                new_value = max(self.minimum, min(self.maximum, new_value))
                if new_value != self._value:
                    self._value = new_value
                    self.display.setText(str(self._value))
                    self.valueChanged.emit(self._value)
                else:
                    # Если значение не изменилось, все равно обновляем текст (на случай если вводили что-то некорректное)
                    self.display.setText(str(self._value))
            except ValueError:
                # Если ввод некорректен, восстанавливаем текущее значение
                self.display.setText(str(self._value))
        else:
            # Если поле пустое, восстанавливаем текущее значение
            self.display.setText(str(self._value))
    
    def setValue(self, value):
        self._value = max(self.minimum, min(self.maximum, value))
        self.display.setText(str(self._value))
    
    def value(self):
        return self._value


class StepperWidget(QWidget):
    # Виджет: число + кнопки -/+ как в дизайне (старая версия)
    valueChanged = Signal(int)
    
    def __init__(self, value=40, minimum=8, maximum=400, parent=None, label_text=""):
        super().__init__()
        self._value = value
        self.minimum = minimum
        self.maximum = maximum
        self.parent_window = parent
        self.label_text = label_text
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.display = NumberDisplay(str(value))
        self.btn_minus = RoundButton("-")
        self.btn_plus = RoundButton("+")
        
        layout.addWidget(self.display)
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.btn_plus)
        
        self.btn_minus.clicked.connect(self.decrease)
        self.btn_plus.clicked.connect(self.increase)
        self.display.clicked.connect(self.on_display_clicked)
        
    def on_display_clicked(self):
        """Открывает диалог для ввода числа"""
        if self.parent_window is None:
            return
        new_val, ok = QInputDialog.getInt(
            self.parent_window,
            self.label_text or "введите значение",
            self.label_text or "введите значение",
            self._value,
            self.minimum,
            self.maximum,
            1
        )
        if ok:
            self.setValue(new_val)
        
    def value(self):
        return self._value
        
    def setValue(self, v):
        v = max(self.minimum, min(self.maximum, int(v)))
        if v != self._value:
            self._value = v
            self.display.setText(str(v))
            self.valueChanged.emit(v)
            
    def increase(self):
        self.setValue(self._value + 1)
        
    def decrease(self):
        self.setValue(self._value - 1)

class CustomSlider(QWidget):
    # Кастомный слайдер как в дизайне: тонкая линия + круглый handle
    valueChanged = Signal(float)
    
    def __init__(self, minimum=0.0, maximum=1.0, value=0.5):
        super().__init__()
        self.minimum = minimum
        self.maximum = maximum
        self._value = value
        self.handle_radius = 6  # Радиус кружка
        self.padding = self.handle_radius  # Отступы слева и справа для кружка
        self.setFixedHeight(12)
        self.setMinimumWidth(347)
        
    def value(self):
        return self._value
        
    def setValue(self, v):
        v = max(self.minimum, min(self.maximum, float(v)))
        if v != self._value:
            self._value = v
            self.update()
            self.valueChanged.emit(v)
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Линия слайдера (с отступами для кружка)
        pen = QPen(QColor(255, 255, 255), 1)
        painter.setPen(pen)
        y = self.height() // 2
        line_start = self.padding
        line_end = self.width() - self.padding
        painter.drawLine(line_start, y, line_end, y)
        
        # Handle (белый круг) - с учетом отступов
        t = (self._value - self.minimum) / (self.maximum - self.minimum)
        x = int(line_start + t * (line_end - line_start))
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(x - self.handle_radius, y - self.handle_radius, 
                           self.handle_radius * 2, self.handle_radius * 2)
        
    def mousePressEvent(self, event):
        self._updateFromMouse(event.pos().x())
        
    def mouseMoveEvent(self, event):
        self._updateFromMouse(event.pos().x())
        
    def _updateFromMouse(self, x):
        # Учитываем отступы при расчете позиции
        line_start = self.padding
        line_end = self.width() - self.padding
        x_clamped = max(line_start, min(line_end, x))
        t = (x_clamped - line_start) / (line_end - line_start)
        new_val = self.minimum + t * (self.maximum - self.minimum)
        self.setValue(new_val)

class CustomCheckbox(QCheckBox):
    # Чекбокс как в дизайне: белый квадрат 23x23
    def __init__(self, text=""):
        super().__init__(text)

class RoundedPreviewContainer(QWidget):
    # Контейнер со скругленными углами для preview
    def __init__(self):
        super().__init__()
        self.border_radius = 30
        
        # Layout для preview
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.preview = PreviewArea()
        layout.addWidget(self.preview)
        
    def resizeEvent(self, event):
        """Обновляем маску при изменении размера"""
        super().resizeEvent(event)
        self._update_mask()
        
    def _update_mask(self):
        """Создает маску со скругленными углами"""
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self.border_radius, self.border_radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
        
    def paintEvent(self, event):
        """Рисуем скругленный фон с антиалиасингом"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Создаем скругленный прямоугольник
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self.border_radius, self.border_radius)
        
        # Заливаем черным
        painter.fillPath(path, QColor(0, 0, 0))


class PreviewArea(QScrollArea):
    # Область превью с зумом
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.label = QLabel(alignment=Qt.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setWidget(self.label)
        self._qimage = None
        self.zoom = 1.0
        
        # Делаем фон прозрачным, т.к. контейнер рисует фон
        self.setStyleSheet("background: transparent; border: none;")
        self.viewport().setStyleSheet("background: black;")
        
    def set_image(self, qimage: QImage):
        self._qimage = qimage
        self._apply_zoom()
        
    def _apply_zoom(self):
        if self._qimage is None:
            self.label.clear()
            return
        pm = QPixmap.fromImage(self._qimage)
        w = max(1, int(round(pm.width() * self.zoom)))
        h = max(1, int(round(pm.height() * self.zoom)))
        spm = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(spm)
        self.label.resize(spm.size())
        
    def wheelEvent(self, e):
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            dy = e.angleDelta().y()
            factor = 1.1 if dy > 0 else 1/1.1
            self.zoom = max(0.1, min(8.0, self.zoom * factor))
            self._apply_zoom()
            e.accept()
        else:
            super().wheelEvent(e)

class FullscreenPreview(QWidget):
    # Второе окно для проекции
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCI-inator - Preview")
        self.label = QLabel(alignment=Qt.AlignCenter)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.label)
        self._qimage = None
        self._pixmap = None
        self._fullscreen = False
        self.setStyleSheet("background:#000;")
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.resize(960, 540)
        
    def set_image(self, qimage: QImage):
        self._qimage = qimage
        if qimage is None:
            self.label.clear()
            return
        self._pixmap = QPixmap.fromImage(qimage)
        self._apply_fit()
        
    def _apply_fit(self):
        if self._pixmap is None:
            return
        spm = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(spm)
        
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_fit()
        
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape,):
            if self._fullscreen:
                self.toggle_fullscreen()
            else:
                self.close()
        elif e.key() in (Qt.Key_F, Qt.Key_F11):
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(e)
            
    def toggle_fullscreen(self):
        if not self._fullscreen:
            self._fullscreen = True
            self.showFullScreen()
        else:
            self._fullscreen = False
            self.showNormal()
            
    def show_on_second_screen(self):
        app = QApplication.instance()
        screens = app.screens()
        if len(screens) > 1:
            geom = screens[1].geometry()
            self.setGeometry(geom)
        self.show()

class LoaderDialog(QDialog):
    # Диалог прогресса экспорта
    cancel_requested = Signal()
    
    def __init__(self, title="render…"):
        super().__init__()
        self.setWindowTitle(title)
        self.setModal(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(20,20,20,20)
        v.setSpacing(12)
        self.lbl = QLabel("render… ⠋")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.pbar = QProgressBar()
        self.pbar.setRange(0,100)
        self.pbar.setValue(0)
        self.btn = QPushButton("cancel")
        self.btn.clicked.connect(self.cancel_requested.emit)
        v.addWidget(self.lbl)
        v.addWidget(self.pbar)
        v.addWidget(self.btn)
        self.frames = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self.idx = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._spin)
        self.timer.start(80)
        
    def _spin(self):
        self.idx = (self.idx + 1) % len(self.frames)
        self.lbl.setText(f"render… {self.frames[self.idx]}")
        
    def set_progress(self, pct:int):
        self.pbar.setValue(int(max(0,min(100,pct))))

class ExportWorker(QThread):
    # Поток экспорта
    progress = Signal(int)
    error = Signal(str)
    done = Signal(str)
    
    def __init__(self, main, fmt, fn, frames, fps, upscale, target_w, target_h, loop, crf):
        super().__init__()
        self.main = main
        self.fmt = fmt
        self.fn = fn
        self.frames = frames
        self.fps = fps
        self.upscale = upscale
        self.target_w = target_w
        self.target_h = target_h
        self.loop = loop
        self.crf = crf
        self._cancel = False
        
    def cancel(self):
        self._cancel = True
        
    def run(self):
        try:
            export_font = self.main._load_font(self.main.font_name, self.main.anim_font_px)
            cw, ch = self.main._measure_cell(export_font)
            out = []
            
            # Для экспорта НЕ используем кэш и downsampling - максимальное качество
            # Детеминированный таймлайн: t шаг = (1 / экспортный FPS) * (speed/100)
            speed_mul = max(0.0, float(self.main.animation_speed_percent) / 100.0)
            dt_export = (1.0 / max(1, self.fps)) * speed_mul
            start_t = 0.0
            for i in range(self.frames):
                if self._cancel:
                    return
                t_now = start_t + i * dt_export
                
                # Обновляем shake для каждого кадра
                if self.main.postfx.crt_enabled and self.main.postfx.crt_shake > 0:
                    self.main.postfx.update_shake()
                
                # If exporting from GL preview and available, try grabbing GPU frame
                if getattr(self.main, 'chk_export_gl', None) is not None and self.main.chk_export_gl.isChecked() \
                   and getattr(self.main, 'gl_preview', None) is not None and self.main.gl_preview.isVisible():
                    # render CPU path to keep timing, then read GL frame
                    _ = self.main.render_frame_pil(
                        t_now, 
                        font=export_font, 
                        cell_w=cw, 
                        cell_h=ch,
                        use_cache=False,
                        for_preview=False
                    )
                    rgb = self.main.gl_preview.get_last_frame_rgb()
                    if rgb is not None:
                        im = Image.fromarray(rgb, 'RGB')
                    else:
                        im = self.main.render_frame_pil(
                            t_now, 
                            font=export_font, 
                            cell_w=cw, 
                            cell_h=ch,
                            use_cache=False,
                            for_preview=False
                        )
                else:
                    im = self.main.render_frame_pil(
                        t_now, 
                    font=export_font, 
                    cell_w=cw, 
                    cell_h=ch,
                    use_cache=False,
                    for_preview=False
                    )
                
                if self.target_w and self.target_h:
                    im = im.resize((self.target_w, self.target_h), Image.NEAREST)
                if abs(self.upscale-1.0) > 1e-6:
                    tw = int(im.width * self.upscale)
                    th = int(im.height * self.upscale)
                    im = im.resize((tw, th), Image.NEAREST)
                
                # Применяем PostFX для экспорта
                im = self.main.postfx.apply_export_fx(im)
                
                out.append(np.array(im.convert("RGB")))
                self.progress.emit(int((i+1)*100/self.frames))
                
            # Сохраняем
            if self.fmt == "GIF":
                import imageio.v3 as iio
                dur = max(10, int(1000 / self.fps))
                iio.imwrite(self.fn, out, format="GIF", duration=dur/1000.0, loop=0 if self.loop else 1)
            else:
                # MP4 экспорт с fallback методами
                success = False
                last_error = None
                
                # Метод 1: Пробуем imageio (обычно работает)
                if not success:
                    try:
                        import imageio
                        writer = None
                        try:
                            writer = imageio.get_writer(
                                self.fn, 
                                fps=self.fps, 
                                codec='libx264',
                                quality=10,
                                ffmpeg_log_level='error',
                                pixelformat='yuv420p',
                                macro_block_size=1,
                                ffmpeg_params=['-crf', str(self.crf)]
                            )
                            
                            for idx, fr in enumerate(out):
                                if self._cancel:
                                    break
                                writer.append_data(fr)
                            success = True
                                    
                        finally:
                            if writer is not None:
                                try:
                                    writer.close()
                                except:
                                    pass
                                    
                            if self._cancel and os.path.exists(self.fn):
                                try:
                                    os.remove(self.fn)
                                except:
                                    pass
                                return
                                
                    except PermissionError as e:
                        last_error = f"Метод 1 (imageio): {e}"
                    except Exception as e:
                        last_error = f"Метод 1 (imageio): {e}"
                
                # Метод 2: Пробуем OpenCV (fallback)
                if not success:
                    try:
                        import cv2
                        
                        if len(out) == 0:
                            raise Exception("Нет кадров для записи")
                            
                        h, w = out[0].shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        writer = cv2.VideoWriter(self.fn, fourcc, float(self.fps), (w, h))
                        
                        if not writer.isOpened():
                            raise Exception("Не удалось открыть VideoWriter")
                        
                        for fr in out:
                            if self._cancel:
                                break
                            # OpenCV использует BGR вместо RGB
                            bgr = cv2.cvtColor(fr, cv2.COLOR_RGB2BGR)
                            writer.write(bgr)
                        
                        writer.release()
                        success = True
                        
                    except ImportError:
                        last_error = "Метод 2 (OpenCV): не установлен. Установите: pip install opencv-python"
                    except Exception as e:
                        last_error = f"Метод 2 (OpenCV): {e}"
                
                # Если ничего не сработало - выдаем ошибку с инструкциями
                if not success:
                    error_msg = "Не удалось экспортировать MP4. Попробуйте:\n\n"
                    error_msg += "1. Запустите программу от Администратора\n"
                    error_msg += "2. Добавьте ffmpeg в исключения антивируса:\n"
                    error_msg += "   Путь: C:\\Users\\mikha\\AppData\\Roaming\\Python\\Python313\\site-packages\\imageio_ffmpeg\\binaries\\\n\n"
                    error_msg += "3. Установите OpenCV: pip install opencv-python\n\n"
                    error_msg += "4. Используйте формат GIF вместо MP4\n\n"
                    error_msg += f"Последняя ошибка: {last_error}"
                    raise Exception(error_msg)
                        
            self.done.emit(self.fn)
            
        except Exception as e:
            import traceback
            error_text = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error.emit(error_text)

# ==================== POST FX MANAGER ====================

class PostFXManager:
    """
    Менеджер постэффектов для ASCII анимации
    - Preview: Qt эффекты (GPU, fast)
    - Export: PIL эффекты (CPU, quality)
    """
    def __init__(self):
        # CRT параметры
        self.crt_enabled = False
        self.crt_scanlines = 0.5
        self.crt_vignette = 0.7
        self.crt_rgb_shift = 0.2
        self.crt_curvature = 0.0
        self.crt_shake = 0.0  # Интенсивность тряски
        self.crt_shake_offset_x = 0  # Текущий сдвиг по X
        self.crt_shake_offset_y = 0  # Текущий сдвиг по Y
        
        # Glow параметры
        self.glow_enabled = False
        self.glow_intensity = 0.8
        self.glow_radius = 20
        self.glow_bloom = 0.6
        
        # Режим
        self.use_gpu_preview = True  # Qt эффекты для preview (быстро)
        self.accurate_preview = False  # PIL эффекты для preview (точно, как export)
        self.full_quality_export = True  # PIL эффекты для export
        
    def update_shake(self):
        """Обновляет случайное смещение для тряски CRT"""
        if self.crt_shake > 0:
            import random
            max_offset = int(self.crt_shake * 5)
            self.crt_shake_offset_x = random.randint(-max_offset, max_offset)
            self.crt_shake_offset_y = random.randint(-max_offset, max_offset)
        else:
            self.crt_shake_offset_x = 0
            self.crt_shake_offset_y = 0
    
    def apply_preview_fx(self, qimage: QImage) -> QImage:
        """
        Применяет эффекты для preview
        - accurate_preview = True: PIL эффекты (точно, как export)
        - accurate_preview = False: Qt эффекты (быстро)
        """
        if not self.crt_enabled and not self.glow_enabled:
            return qimage
        
        # Режим Accurate Preview - используем PIL (как export)
        if self.accurate_preview:
            # QImage -> PIL через numpy (самый надежный способ)
            qimage = qimage.convertToFormat(QImage.Format_RGBA8888)
            width = qimage.width()
            height = qimage.height()
            ptr = qimage.constBits()
            
            import numpy as np
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4))
            pil_img = Image.fromarray(arr.copy(), 'RGBA')
            
            # Применяем PIL эффекты (те же что в export)
            pil_img = self.apply_export_fx(pil_img)
            
            # Конвертируем обратно PIL -> QImage
            data = pil_img.tobytes('raw', 'RGBA')
            result = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
            
            return result.copy()  # Копируем чтобы избежать проблем с памятью
            
        # Быстрый режим - Qt эффекты
        pixmap = QPixmap.fromImage(qimage)
        
        if self.crt_enabled and self.use_gpu_preview:
            pixmap = self._apply_crt_preview(pixmap)
            
        if self.glow_enabled and self.use_gpu_preview:
            pixmap = self._apply_glow_preview(pixmap)
            
        return pixmap.toImage()
        
    def _apply_crt_preview(self, pixmap: QPixmap) -> QPixmap:
        """CRT эффекты для preview (Qt)"""
        # Создаем результат с учетом shake
        width = pixmap.width()
        height = pixmap.height()
        
        result = QPixmap(width, height)
        result.fill(QColor(0, 0, 0))  # Черный фон
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Рисуем оригинал с учетом shake
        offset_x = self.crt_shake_offset_x
        offset_y = self.crt_shake_offset_y
        painter.drawPixmap(offset_x, offset_y, pixmap)
        
        # Scanlines (более заметные)
        if self.crt_scanlines > 0:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            for y in range(0, height, 2):
                alpha = int(self.crt_scanlines * 180)  # Увеличена видимость
                painter.setPen(QPen(QColor(0, 0, 0, alpha), 1))
                painter.drawLine(0, y, width, y)
                
        # Vignette (более заметная)
        if self.crt_vignette > 0:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            gradient = QRadialGradient(
                width / 2, 
                height / 2,
                max(width, height) * 0.6  # Уменьшен радиус для большей заметности
            )
            gradient.setColorAt(0, QColor(0, 0, 0, 0))
            alpha = int(self.crt_vignette * 200)  # Увеличена интенсивность
            gradient.setColorAt(1, QColor(0, 0, 0, alpha))
            painter.fillRect(result.rect(), gradient)
            
        painter.end()
        return result
        
    def _apply_glow_preview(self, pixmap: QPixmap) -> QPixmap:
        """Glow эффект для preview (Qt - простая яркость)"""
        # Для preview делаем простое увеличение яркости
        result = QPixmap(pixmap.size())
        result.fill(Qt.transparent)
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Рисуем оригинал
        painter.drawPixmap(0, 0, pixmap)
        
        # Добавляем легкий "glow" через overlay
        if self.glow_intensity > 0:
            painter.setCompositionMode(QPainter.CompositionMode_Plus)
            alpha = int(min(255, self.glow_intensity * 80))
            painter.fillRect(result.rect(), QColor(255, 255, 255, alpha))
        
        painter.end()
        return result
        
    def apply_export_fx(self, pil_image: Image.Image) -> Image.Image:
        """
        Применяет эффекты для export (PIL - качество)
        """
        if not self.crt_enabled and not self.glow_enabled:
            return pil_image
            
        result = pil_image.copy()
        
        # CRT эффекты
        if self.crt_enabled and self.full_quality_export:
            result = self._apply_crt_export(result)
            
        # Glow эффекты
        if self.glow_enabled and self.full_quality_export:
            result = self._apply_glow_export(result)
            
        return result
        
    def _apply_crt_export(self, img: Image.Image) -> Image.Image:
        """CRT эффекты для export (PIL - полное качество)"""
        result = img.convert('RGBA')
        width, height = result.size
        
        # Shake (сдвиг изображения)
        if self.crt_shake > 0:
            # Создаем новое изображение с черным фоном
            shaked = Image.new('RGBA', (width, height), (0, 0, 0, 255))
            # Вставляем оригинал со смещением
            shaked.paste(result, (self.crt_shake_offset_x, self.crt_shake_offset_y))
            result = shaked
        
        # Scanlines
        if self.crt_scanlines > 0:
            overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            alpha = int(self.crt_scanlines * 150)
            for y in range(0, height, 2):
                draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
            result = Image.alpha_composite(result, overlay)
            
        # Vignette (оптимизированная с numpy)
        if self.crt_vignette > 0:
            # Создаем координатную сетку
            y_coords, x_coords = np.ogrid[:height, :width]
            center_x, center_y = width // 2, height // 2
            
            # Вычисляем расстояние от центра
            dist_from_center = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)
            max_dist = np.sqrt(center_x**2 + center_y**2)
            
            # Нормализуем и применяем vignette
            vignette_mask = (dist_from_center / max_dist) * self.crt_vignette
            vignette_mask = np.clip(vignette_mask, 0, 1)
            
            # Создаем темный overlay
            overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            overlay_arr = np.array(overlay)
            overlay_arr[:, :, 3] = (vignette_mask * 255).astype(np.uint8)
            overlay = Image.fromarray(overlay_arr, 'RGBA')
            
            result = Image.alpha_composite(result, overlay)
            
        # RGB Shift (хроматическая аберрация)
        if self.crt_rgb_shift > 0:
            shift = int(self.crt_rgb_shift * 5)
            r, g, b, a = result.split()
            
            # Сдвигаем каналы
            r = Image.eval(r, lambda x: x)
            r_shifted = Image.new('L', (width, height), 0)
            r_shifted.paste(r, (shift, 0))
            
            b_shifted = Image.new('L', (width, height), 0)
            b_shifted.paste(b, (-shift, 0))
            
            result = Image.merge('RGBA', (r_shifted, g, b_shifted, a))
            
        return result.convert('RGB')
        
    def _apply_glow_export(self, img: Image.Image) -> Image.Image:
        """Glow эффект для export (PIL - bloom)"""
        from PIL import ImageFilter, ImageChops
        import numpy as np
        
        result = img.convert('RGBA')
        
        # Шаг 1: Извлекаем яркие участки (threshold)
        # Конвертируем в numpy для threshold
        arr = np.array(result)
        
        # Создаем маску ярких пикселей
        # Берем среднюю яркость RGB каналов
        brightness = arr[:,:,:3].mean(axis=2)
        threshold = 128 * (1.0 - self.glow_bloom)  # bloom влияет на порог
        bright_mask = brightness > threshold
        
        # Создаем слой только с яркими пикселями
        bloom_arr = arr.copy()
        bloom_arr[~bright_mask] = [0, 0, 0, 0]  # Затемняем тусклые пиксели
        
        bloom = Image.fromarray(bloom_arr, 'RGBA')
        
        # Шаг 2: Усиливаем яркость bloom слоя
        enhancer = ImageEnhance.Brightness(bloom)
        bloom = enhancer.enhance(1.0 + self.glow_intensity)
        
        # Шаг 3: Размываем bloom (несколько проходов для лучшего эффекта)
        blur_radius = self.glow_radius
        for _ in range(2):  # Двойное размытие для мягкого свечения
            bloom = bloom.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # Шаг 4: Additive blending (добавляем свечение поверх)
        # Конвертируем обратно в RGB для смешивания
        result_rgb = result.convert('RGB')
        bloom_rgb = bloom.convert('RGB')
        
        # Additive blend: просто складываем и обрезаем
        result_arr = np.array(result_rgb, dtype=np.float32)
        bloom_arr = np.array(bloom_rgb, dtype=np.float32)
        
        # Смешиваем с учетом интенсивности
        glow_strength = self.glow_intensity * 0.5
        final_arr = result_arr + bloom_arr * glow_strength
        final_arr = np.clip(final_arr, 0, 255).astype(np.uint8)
        
        return Image.fromarray(final_arr, 'RGB')

# ==================== SETTINGS DIALOG ====================

class SettingsOverlay(QWidget):
    # Full-screen overlay with blur and darken effect
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setStyleSheet("background: transparent;")
        
    def paintEvent(self, event):
        # Draw semi-transparent dark overlay
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))  # 70% opacity black overlay


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Settings")
        self.setFixedSize(538, 630)  # Match Figma design
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        
        # Хранилище настроек (инициализируем из темы главного окна)
        if parent and hasattr(parent, 'get_ui_theme'):
            theme = parent.get_ui_theme()
            self.colors = {
                'ui_bg': theme.get('ui_bg', '#3F3F3F'),
                'ui_text': theme.get('ui_text', '#FFFFFF'),
                'button_bg': theme.get('button_bg', '#FFFFFF'),
                'button_border': theme.get('button_border', '#FFFFFF'),
                'button_text': theme.get('button_text', '#000000'),
                'accent': theme.get('accent', '#FFFFFF'),
            }
        else:
            self.colors = {
                'ui_bg': '#3F3F3F',
                'ui_text': '#FFFFFF',
                'button_bg': '#FFFFFF',
                'button_border': '#FFFFFF',
                'button_text': '#000000',
                'accent': '#FFFFFF'
            }
        
        # Получаем текущие настройки из главного окна, если есть
        if parent:
            app = QApplication.instance()
            current_font = app.font()
            self.font_family = current_font.family()
            self.font_size = current_font.pointSize() if current_font.pointSize() > 0 else 16
        else:
            self.font_family = "Helvetica Neue"
            self.font_size = 16
            
        self.audio_device = None
        self.has_changes = False  # Track unsaved changes
        
        self._build_ui()
        
    def _build_ui(self):
        # Main container with rounded background
        main_container = QWidget(self)
        main_container.setFixedSize(538, 630)
        main_container.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)
        
        layout = QVBoxLayout(main_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)  # 15px gap between tabs and content
        
        # Custom tab bubbles
        self.tab_buttons = []
        self.current_tab = 0
        
        tabs_container = QWidget()
        tabs_container.setFixedHeight(46)
        tabs_container.setStyleSheet("background: transparent;")
        tabs_layout = QHBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(18)  # Space between tabs
        tabs_layout.setAlignment(Qt.AlignLeft)
        
        # Create tab bubbles
        tab_names = ["Interface", "Audio", "Performance"]
        for i, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setFixedHeight(46)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            btn.setFont(self.get_font("Helvetica Neue Medium", 20))
            btn.setCursor(Qt.PointingHandCursor)
            self.tab_buttons.append(btn)
            tabs_layout.addWidget(btn)
        
        # Apply initial styles after all buttons are created
        self._update_tab_styles()
        
        layout.addWidget(tabs_container)
        
        # Content area (stacked widget)
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("background: transparent;")
        
        # Create tabs
        interface_tab = self._create_interface_tab()
        audio_tab = self._create_audio_tab()
        performance_tab = self._create_performance_tab()
        
        self.content_stack.addWidget(interface_tab)
        self.content_stack.addWidget(audio_tab)
        self.content_stack.addWidget(performance_tab)
        
        layout.addWidget(self.content_stack)
        
        # Bottom buttons
        buttons_container = QWidget()
        buttons_container.setFixedHeight(44)
        buttons_container.setStyleSheet("background: transparent;")
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(20)
        
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(259, 44)
        btn_close.clicked.connect(self.reject)
        btn_close.setStyleSheet("""
            QPushButton {
                background: #000000;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #222222;
            }
        """)
        btn_close.setFont(self.get_font("Helvetica Neue", 16))
        
        btn_apply = QPushButton("Apply")
        btn_apply.setFixedSize(259, 44)
        btn_apply.clicked.connect(self.apply_settings)
        btn_apply.setFont(self.get_font("Helvetica Neue", 16))
        self.btn_apply = btn_apply  # Store reference
        self._update_apply_button_style()  # Set initial style
        
        buttons_layout.addWidget(btn_close)
        buttons_layout.addWidget(btn_apply)
        
        layout.addWidget(buttons_container)
        
        # Center the dialog on screen
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - 538) // 2
            y = parent_geo.y() + (parent_geo.height() - 630) // 2
            self.move(x, y)
    
    def _get_tab_style(self, active):
        # Tab bubble style - active 100%, inactive 30%
        if active:
            return """
                QPushButton {
                    background: rgba(0,0,0,1.0);
                    color: white;
                    border: none;
                    border-radius: 30px;
                    padding: 13px 22px;
                    font-size: 20px;
                    font-weight: 500;
                    font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                }
                QPushButton:hover {
                    background: rgba(0,0,0,1);
                }
            """
        else:
            return """
                QPushButton {
                    background: rgba(0,0,0,0.3);
                    color: white;
                    border: none;
                    border-radius: 30px;
                    padding: 13px 22px;
                    font-size: 20px;
                    font-weight: 500;
                    font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                }
                QPushButton:hover {
                    background: rgba(0,0,0,0.4);
                }
            """
    
    def _update_tab_styles(self):
        # Update all tab button styles based on current_tab
        for i, btn in enumerate(self.tab_buttons):
            is_active = (i == self.current_tab)
            btn.setStyleSheet(self._get_tab_style(is_active))
    
    def _switch_tab(self, index):
        # Switch tab and update styles
        self.current_tab = index
        self.content_stack.setCurrentIndex(index)
        self._update_tab_styles()
    
    def get_font(self, name, size):
        # Helper to get font
        font = QFont(name, size)
        return font
    
    def _mark_as_changed(self):
        # Mark settings as changed (unsaved)
        if not self.has_changes:
            self.has_changes = True
            self._update_apply_button_style()
    
    def _update_apply_button_style(self):
        # Update apply button color based on has_changes
        if self.has_changes:
            # Yellow for unsaved changes
            self.btn_apply.setStyleSheet("""
                QPushButton {
                    background: #FFCC00;
                    color: black;
                    border: none;
                    border-radius: 20px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: #FFD633;
                }
            """)
        else:
            # White for no changes
            self.btn_apply.setStyleSheet("""
                QPushButton {
                    background: white;
                    color: black;
                    border: none;
                    border-radius: 20px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: #EEEEEE;
                }
            """)
        
    def _create_interface_tab(self):
        # Main tab widget
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)  # 10px between containers
        
        # === CONTAINER 1: цвет интерфейса ===
        color_container = QWidget()
        color_container.setFixedSize(538, 282)
        color_container.setStyleSheet("""
            QWidget {
                background: #000000;
                border-radius: 30px;
            }
        """)
        color_layout = QVBoxLayout(color_container)
        color_layout.setContentsMargins(20, 20, 20, 20)
        color_layout.setSpacing(20)
        
        # Title
        color_title = QLabel("Interface color")
        color_title.setFont(self.get_font("Helvetica Neue", 16))
        color_title.setStyleSheet("color: rgba(66,66,66,1); background: transparent;")
        color_layout.addWidget(color_title)
        
        # Color fields
        color_fields = [
            ("UI background", 'ui_bg'),
            ("UI text", 'ui_text'),
            ("Button borders", 'button_border'),
            ("Button text", 'button_text')
        ]
        
        # Store widgets for color picker updates
        self.color_inputs = {}
        self.color_swatches = {}
        
        for label_text, key in color_fields:
            row = QWidget()
            row.setFixedHeight(44)
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            
            # Label
            label = QLabel(label_text)
            label.setFont(self.get_font("Helvetica Neue", 16))
            label.setStyleSheet("color: white; background: transparent;")
            label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            row_layout.addWidget(label)
            
            row_layout.addStretch()
            
            # Right side container (HEX input + swatch) - fixed width for alignment
            right_container = QWidget()
            right_container.setFixedSize(147, 44)  # 93 (hex) + 10 (spacing) + 44 (swatch) = 147
            right_container.setStyleSheet("background: transparent;")
            right_layout = QHBoxLayout(right_container)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(10)
            
            # HEX input field
            hex_input = QLineEdit(self.colors[key])
            hex_input.setFixedSize(93, 44)
            hex_input.setFont(self.get_font("Helvetica Neue", 16))
            hex_input.setStyleSheet("""
                QLineEdit {
                    background: transparent;
                    color: white;
                    border: 2px solid white;
                    border-radius: 20px;
                    padding: 0px 14px;
                }
            """)
            hex_input.setAlignment(Qt.AlignCenter)
            hex_input.textChanged.connect(lambda text, k=key: self._on_hex_input_changed(k, text))
            self.color_inputs[key] = hex_input
            
            # Color swatch (round button)
            swatch = QPushButton()
            swatch.setFixedSize(44, 44)
            swatch.setStyleSheet(f"""
                QPushButton {{
                    background: {self.colors[key]};
                    border: 2px solid white;
                    border-radius: 22px;
                }}
                QPushButton:hover {{
                    border: 3px solid white;
                }}
            """)
            swatch.setCursor(Qt.PointingHandCursor)
            swatch.clicked.connect(lambda checked, k=key: self._pick_color_new(k))
            self.color_swatches[key] = swatch
            
            right_layout.addWidget(hex_input)
            right_layout.addWidget(swatch)
            
            row_layout.addWidget(right_container)
            
            color_layout.addWidget(row)
        
        layout.addWidget(color_container)
        
        # === CONTAINER 2: шрифт ui ===
        font_container = QWidget()
        font_container.setFixedSize(538, 174)
        font_container.setStyleSheet("""
            QWidget {
                background: #000000;
                border-radius: 30px;
            }
        """)
        font_layout = QVBoxLayout(font_container)
        font_layout.setContentsMargins(20, 20, 20, 20)
        font_layout.setSpacing(20)
        
        # Title
        font_title = QLabel("UI font")
        font_title.setFont(self.get_font("Helvetica Neue", 16))
        font_title.setStyleSheet("color: rgba(66,66,66,1); background: transparent;")
        font_layout.addWidget(font_title)
        
        # Font dropdown row
        font_dropdown_row = QWidget()
        font_dropdown_row.setFixedHeight(44)
        font_dropdown_row.setStyleSheet("background: transparent;")
        font_dropdown_layout = QHBoxLayout(font_dropdown_row)
        font_dropdown_layout.setContentsMargins(0, 0, 0, 0)
        font_dropdown_layout.setSpacing(0)
        
        # Font selector dropdown
        font_combo = QComboBox()
        font_combo.setFixedSize(498, 44)
        available_fonts = sorted(QFontDatabase.families())
        font_combo.addItems(available_fonts)
        
        if self.font_family in available_fonts:
            font_combo.setCurrentText(self.font_family)
        elif "Helvetica Neue" in available_fonts:
            font_combo.setCurrentText("Helvetica Neue")
            self.font_family = "Helvetica Neue"
        
        self.font_combo = font_combo
        font_combo.currentTextChanged.connect(self._on_font_changed)
        font_combo.setFont(self.get_font("Helvetica Neue", 16))
        font_combo.setStyleSheet("""
            QComboBox {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-radius: 20px;
                padding: 0px 14px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background: #000000;
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                selection-background-color: #333333;
            }
        """)
        
        font_dropdown_layout.addWidget(font_combo)
        font_layout.addWidget(font_dropdown_row)
        
        # Font size (кегль) row
        size_row = QWidget()
        size_row.setFixedHeight(44)
        size_row.setStyleSheet("background: transparent;")
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(0)
        
        # Label
        size_label = QLabel("Size")
        size_label.setFont(self.get_font("Helvetica Neue", 16))
        size_label.setStyleSheet("color: white; background: transparent;")
        size_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        size_layout.addWidget(size_label)
        
        size_layout.addStretch()
        
        # Right side: Number display + stepper pill
        right_size_container = QWidget()
        right_size_container.setFixedHeight(44)
        right_size_container.setStyleSheet("background: transparent;")
        right_size_layout = QHBoxLayout(right_size_container)
        right_size_layout.setContentsMargins(0, 0, 0, 0)
        right_size_layout.setSpacing(10)
        
        # Number display (editable)
        size_display = QLineEdit(str(self.font_size))
        size_display.setFixedSize(68, 44)
        size_display.setFont(self.get_font("Helvetica Neue Bold", 24))
        size_display.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                padding: 0px;
            }
        """)
        size_display.setAlignment(Qt.AlignCenter)
        size_display.setValidator(QIntValidator(8, 72))
        size_display.textChanged.connect(lambda: self._mark_as_changed())
        size_display.editingFinished.connect(self._on_size_text_edited)
        size_display.returnPressed.connect(self._on_size_text_edited)
        self.size_display = size_display
        
        # Stepper pill (- and + buttons)
        stepper_container = QWidget()
        stepper_container.setFixedSize(88, 40)
        stepper_container.setStyleSheet("background: transparent;")
        stepper_layout = QHBoxLayout(stepper_container)
        stepper_layout.setContentsMargins(0, 0, 0, 0)
        stepper_layout.setSpacing(0)
        
        btn_minus = QPushButton("-")
        btn_minus.setFixedSize(44, 40)
        btn_minus.setFont(self.get_font("Helvetica Neue", 20))
        btn_minus.clicked.connect(lambda: self._change_font_size(-1))
        btn_minus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-top-left-radius: 20px;
                border-bottom-left-radius: 20px;
                border-right: 1px solid white;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        
        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(44, 40)
        btn_plus.setFont(self.get_font("Helvetica Neue", 20))
        btn_plus.clicked.connect(lambda: self._change_font_size(1))
        btn_plus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-top-right-radius: 20px;
                border-bottom-right-radius: 20px;
                border-left: 1px solid white;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        
        stepper_layout.addWidget(btn_minus)
        stepper_layout.addWidget(btn_plus)
        
        right_size_layout.addWidget(size_display)
        right_size_layout.addWidget(stepper_container)
        
        size_layout.addWidget(right_size_container)
        
        font_layout.addWidget(size_row)
        
        layout.addWidget(font_container)
        layout.addStretch()
        
        return widget
        
    def _create_audio_tab(self):
        # Main tab widget
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)  # 10px between containers
        
        # === CONTAINER 1: ввод звука ===
        audio_container = QWidget()
        audio_container.setFixedSize(538, 174)
        audio_container.setStyleSheet("""
            QWidget {
                background: #000000;
                border-radius: 30px;
            }
        """)
        audio_layout = QVBoxLayout(audio_container)
        audio_layout.setContentsMargins(20, 20, 20, 20)
        audio_layout.setSpacing(20)
        
        # Title
        audio_title = QLabel("Audio input")
        audio_title.setFont(self.get_font("Helvetica Neue", 16))
        audio_title.setStyleSheet("color: rgba(66,66,66,1); background: transparent;")
        audio_layout.addWidget(audio_title)
        
        # Device selector row
        device_row = QWidget()
        device_row.setFixedHeight(44)
        device_row.setStyleSheet("background: transparent;")
        device_row_layout = QHBoxLayout(device_row)
        device_row_layout.setContentsMargins(0, 0, 0, 0)
        device_row_layout.setSpacing(0)
        
        # Label
        device_label = QLabel("Select device")
        device_label.setFont(self.get_font("Helvetica Neue", 16))
        device_label.setStyleSheet("color: white; background: transparent;")
        device_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        
        # Device dropdown
        device_combo = QComboBox()
        device_combo.setFixedSize(498, 44)
        device_combo.addItem("Select device")
        
        # Загружаем список аудио-устройств если sounddevice установлен
        if sd is not None:
            try:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    if dev['max_input_channels'] > 0:
                        device_combo.addItem(dev['name'], i)
            except:
                pass
        
        device_combo.currentIndexChanged.connect(lambda: self._mark_as_changed())
        device_combo.setFont(self.get_font("Helvetica Neue", 16))
        device_combo.setStyleSheet("""
            QComboBox {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-radius: 20px;
                padding: 0px 14px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background: #000000;
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                selection-background-color: #333333;
            }
        """)
        
        device_row_layout.addWidget(device_combo)
        audio_layout.addWidget(device_row)
        
        # Gain row (placeholder for future audio gain control)
        gain_row = QWidget()
        gain_row.setFixedHeight(44)
        gain_row.setStyleSheet("background: transparent;")
        gain_row_layout = QHBoxLayout(gain_row)
        gain_row_layout.setContentsMargins(0, 0, 0, 0)
        gain_row_layout.setSpacing(0)
        
        # Label
        gain_label = QLabel("Gain")
        gain_label.setFont(self.get_font("Helvetica Neue", 16))
        gain_label.setStyleSheet("color: white; background: transparent;")
        gain_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        gain_row_layout.addWidget(gain_label)
        
        gain_row_layout.addStretch()
        
        # Right side: Number display + stepper pill
        right_gain_container = QWidget()
        right_gain_container.setFixedHeight(44)
        right_gain_container.setStyleSheet("background: transparent;")
        right_gain_layout = QHBoxLayout(right_gain_container)
        right_gain_layout.setContentsMargins(0, 0, 0, 0)
        right_gain_layout.setSpacing(10)
        
        # Number display
        gain_display = QLineEdit("40")
        gain_display.setFixedSize(68, 44)
        gain_display.setFont(self.get_font("Helvetica Neue Bold", 24))
        gain_display.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                padding: 0px;
            }
        """)
        gain_display.setAlignment(Qt.AlignCenter)
        gain_display.setValidator(QIntValidator(0, 100))
        gain_display.textChanged.connect(lambda: self._mark_as_changed())
        
        # Stepper pill
        stepper_container = QWidget()
        stepper_container.setFixedSize(88, 40)
        stepper_container.setStyleSheet("background: transparent;")
        stepper_layout = QHBoxLayout(stepper_container)
        stepper_layout.setContentsMargins(0, 0, 0, 0)
        stepper_layout.setSpacing(0)
        
        btn_minus = QPushButton("-")
        btn_minus.setFixedSize(44, 40)
        btn_minus.setFont(self.get_font("Helvetica Neue", 20))
        btn_minus.clicked.connect(lambda: self._change_gain(-5, gain_display))
        btn_minus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-top-left-radius: 20px;
                border-bottom-left-radius: 20px;
                border-right: 1px solid white;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        
        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(44, 40)
        btn_plus.setFont(self.get_font("Helvetica Neue", 20))
        btn_plus.clicked.connect(lambda: self._change_gain(5, gain_display))
        btn_plus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: 2px solid white;
                border-top-right-radius: 20px;
                border-bottom-right-radius: 20px;
                border-left: 1px solid white;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        
        stepper_layout.addWidget(btn_minus)
        stepper_layout.addWidget(btn_plus)
        
        right_gain_layout.addWidget(gain_display)
        right_gain_layout.addWidget(stepper_container)
        
        gain_row_layout.addWidget(right_gain_container)
        
        audio_layout.addWidget(gain_row)
        
        layout.addWidget(audio_container)
        layout.addStretch()
        
        return widget
    
    def _create_performance_tab(self):
        # Performance tab (placeholder for now)
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Placeholder container
        container = QWidget()
        container.setFixedSize(538, 282)
        container.setStyleSheet("""
            QWidget {
                background: #000000;
                border-radius: 30px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(20)
        
        # Title
        title = QLabel("Performance")
        title.setFont(self.get_font("Helvetica Neue", 16))
        title.setStyleSheet("color: rgba(66,66,66,1); background: transparent;")
        container_layout.addWidget(title)
        
        # Placeholder text
        placeholder = QLabel("Performance settings\nwill be added soon")
        placeholder.setFont(self.get_font("Helvetica Neue", 16))
        placeholder.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent;")
        placeholder.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(placeholder, 1)
        
        layout.addWidget(container)
        layout.addStretch()
        
        return widget
        
    def _create_group(self, title):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 10, 0, 0)
        main_layout.setSpacing(0)
        
        # Заголовок группы
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            color: rgba(255,255,255,0.7);
            font-size: 16px;
            font-weight: light;
            background: transparent;
            padding: 0px 5px;
            margin-left: 15px;
        """)
        title_label.setFixedHeight(20)
        main_layout.addWidget(title_label, 0, Qt.AlignLeft)
        
        # Сам виджет группы с рамкой
        group = QWidget()
        group.setStyleSheet("""
            QWidget {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
                padding: 20px;
            }
        """)
        main_layout.addWidget(group)
        
        return container, group
        
    def _pick_color(self, key, input_field, button):
        color = QColorDialog.getColor(QColor(self.colors[key]), self)
        if color.isValid():
            hex_color = color.name()
            self.colors[key] = hex_color
            input_field.setText(hex_color)
            button.setStyleSheet(f"""
                QPushButton {{
                    background: {hex_color};
                    border: 2px solid white;
                    border-radius: 22px;
                }}
            """)
            
    def _on_size_text_edited(self):
        # Обработчик ручного ввода размера шрифта
        text = self.size_display.text().strip()
        if text:
            try:
                new_size = int(text)
                # Клампим значение в пределах 8-72
                new_size = max(8, min(72, new_size))
                self.font_size = new_size
                self.size_display.setText(str(self.font_size))
            except ValueError:
                # Если ввод некорректен, восстанавливаем текущее значение
                self.size_display.setText(str(self.font_size))
        else:
            # Если поле пустое, восстанавливаем текущее значение
            self.size_display.setText(str(self.font_size))
    
    def _change_font_size(self, delta):
        self.font_size = max(8, min(72, self.font_size + delta))
        self.size_display.setText(str(self.font_size))
        self._mark_as_changed()
    
    def _on_hex_input_changed(self, key, text):
        # Handle HEX input changes
        self.colors[key] = text
        # Update swatch color if valid hex
        if text.startswith('#') and len(text) == 7:
            try:
                self.color_swatches[key].setStyleSheet(f"""
                    QPushButton {{
                        background: {text};
                        border: 2px solid white;
                        border-radius: 22px;
                    }}
                    QPushButton:hover {{
                        border: 3px solid white;
                    }}
                """)
            except:
                pass
        self._mark_as_changed()
    
    def _pick_color_new(self, key):
        # Color picker через обертку с гарантированными кнопками OK/Cancel
        current_color = QColor(self.colors[key])
        picked = self._open_color_picker(current_color)
        if picked is not None and picked.isValid():
            hex_color = picked.name()
            self.colors[key] = hex_color
            # Update input field
            self.color_inputs[key].setText(hex_color)
            # Update swatch
            self.color_swatches[key].setStyleSheet(f"""
                QPushButton {{
                    background: {hex_color};
                    border: 2px solid white;
                    border-radius: 22px;
                }}
                QPushButton:hover {{
                    border: 3px solid white;
                }}
            """)
            self._mark_as_changed()
    
    def _open_color_picker(self, initial_color: 'QColor'):
        # Прямой QColorDialog (нативный), со сбросом стилей — чтобы кнопки и контент точно были
        dlg = QColorDialog(None)  # без родителя, чтобы не наследовать стили
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setOption(QColorDialog.ShowAlphaChannel, False)
        dlg.setOption(QColorDialog.NoButtons, False)
        dlg.setOption(QColorDialog.DontUseNativeDialog, True)  # Qt-версия с кнопками
        dlg.setCurrentColor(initial_color)
        if dlg.exec():
            return dlg.currentColor()
        return None
    
    def _on_font_changed(self, text):
        # Handle font change
        self.font_family = text
        self._mark_as_changed()
    
    def _change_gain(self, delta, display_widget):
        # Change audio gain value
        try:
            current = int(display_widget.text())
            new_value = max(0, min(100, current + delta))
            display_widget.setText(str(new_value))
            self._mark_as_changed()
        except ValueError:
            display_widget.setText("40")
        
    def apply_settings(self):
        # Применяет настройки к приложению
        try:
            app = QApplication.instance()
            
            # Применяем шрифт ко всему приложению
            new_font = QFont(self.font_family, self.font_size)
            app.setFont(new_font)
            
            # Применяем цвета интерфейса в главное окно
            if self.main_window:
                theme = self.main_window.get_ui_theme()
                theme.update({
                    'ui_bg': self.colors.get('ui_bg', theme['ui_bg']),
                    'ui_text': self.colors.get('ui_text', theme['ui_text']),
                    'button_bg': self.colors.get('button_bg', theme['button_bg']),
                    'button_text': self.colors.get('button_text', theme['button_text']),
                    'button_border': self.colors.get('button_border', theme['button_border']),
                    'accent': self.colors.get('accent', theme['accent']),
                })
                self.main_window.apply_ui_theme(theme)
                self.main_window.update()
                # Перерисовываем preview чтобы применить новый шрифт к ASCII
                if hasattr(self.main_window, 'glyph_cache'):
                    self.main_window.glyph_cache.clear()
                if hasattr(self.main_window, 'update_preview'):
                    self.main_window.update_preview(True)
            
            # Reset changes flag and update button style
            self.has_changes = False
            self._update_apply_button_style()
            
            QMessageBox.information(
                self, 
                "settings", 
                f"Settings applied!\n\nFont: {self.font_family}\nSize: {self.font_size}pt"
            )
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "error", 
                f"Failed to apply settings:\n{str(e)}"
            )

# ==================== TAB SYSTEM ====================

class TabBubble(QPushButton):
    # Кнопка-бабл для таба
    def __init__(self, text):
        super().__init__(text)
        self.setCheckable(True)
        self.setFixedHeight(60)
        self.setCursor(Qt.PointingHandCursor)
        # Графический эффект прозрачности для точного контроля opacity
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self.updateStyle()
        self.toggled.connect(self.updateStyle)
    
    def updateStyle(self):
        # Обновляет стиль в зависимости от состояния (активный/неактивный)
        if self.isChecked():
            # Активный таб: 100% opacity, черный фон
            self._opacity_effect.setOpacity(1.0)
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(0,0,0,1);
                    color: white;
                    border: none;
                    border-radius: 30px;
                    padding: 15px 30px;
                    font-size: 20px;
                    font-weight: 500;
                    font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                }
                QPushButton:hover {
                    background: rgba(0,0,0,1);
                }
            """)
        else:
            # Неактивный таб: 30% opacity, черный фон как в основном UI
            self._opacity_effect.setOpacity(0.3)
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(0,0,0,1);
                    color: white;
                    border: none;
                    border-radius: 30px;
                    padding: 15px 30px;
                    font-size: 20px;
                    font-weight: 500;
                    font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                }
                QPushButton:hover {
                    background: rgba(0,0,0,1);
                }
            """)


class ScrollableTabBar(QWidget):
    """Scrollable панель табов со стрелочками"""
    tabChanged = Signal(int)
    
    def __init__(self, tab_names):
        super().__init__()
        self.tab_names = tab_names
        self.current_index = 0
        self.tab_buttons = []
        
        # Виджет не должен растягиваться
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Стрелка влево (круглая кнопка)
        self.btn_left = QPushButton("<")
        self.btn_left.setFixedSize(60, 60)
        self.btn_left.setStyleSheet("""
            QPushButton {
                background: rgba(0,0,0,1);
                color: white;
                border: none;
                font-size: 24px;
                border-radius: 30px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.8);
            }
        """)
        self.btn_left.clicked.connect(self.scrollLeft)
        layout.addWidget(self.btn_left)
        
        # Scrollable область для табов
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFixedHeight(60)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)
        
        # Контейнер для табов
        tabs_container = QWidget()
        tabs_layout = QHBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(10)
        
        # Создаем баблы для каждого таба
        for i, name in enumerate(tab_names):
            btn = TabBubble(name)
            btn.clicked.connect(lambda checked, idx=i: self.selectTab(idx))
            self.tab_buttons.append(btn)
            tabs_layout.addWidget(btn)
        
        scroll_area.setWidget(tabs_container)
        self.scroll_area = scroll_area
        layout.addWidget(scroll_area, 0)
        
        # Стрелка вправо (круглая кнопка)
        self.btn_right = QPushButton(">")
        self.btn_right.setFixedSize(60, 60)
        self.btn_right.setStyleSheet("""
            QPushButton {
                background: rgba(0,0,0,1);
                color: white;
                border: none;
                font-size: 24px;
                border-radius: 30px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.8);
            }
        """)
        self.btn_right.clicked.connect(self.scrollRight)
        layout.addWidget(self.btn_right)
        
        # Выбираем первый таб
        if self.tab_buttons:
            self.tab_buttons[0].setChecked(True)
        
        # Анимация для плавного скролла
        self.scroll_animation = QPropertyAnimation(self.scroll_area.horizontalScrollBar(), b"value")
        self.scroll_animation.setDuration(300)  # 300ms для плавности
        self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
    
    def selectTab(self, index):
        # Выбирает таб по индексу
        if 0 <= index < len(self.tab_buttons):
            # Снимаем выделение со всех табов
            for btn in self.tab_buttons:
                btn.setChecked(False)
            # Выделяем выбранный таб
            self.tab_buttons[index].setChecked(True)
            self.current_index = index
            self.tabChanged.emit(index)
    
    def scrollLeft(self):
        # Плавная прокрутка влево
        scrollbar = self.scroll_area.horizontalScrollBar()
        current_value = scrollbar.value()
        target_value = max(0, current_value - 200)
        
        self.scroll_animation.stop()
        self.scroll_animation.setStartValue(current_value)
        self.scroll_animation.setEndValue(target_value)
        self.scroll_animation.start()
    
    def scrollRight(self):
        # Плавная прокрутка вправо
        scrollbar = self.scroll_area.horizontalScrollBar()
        current_value = scrollbar.value()
        target_value = min(scrollbar.maximum(), current_value + 200)
        
        self.scroll_animation.stop()
        self.scroll_animation.setStartValue(current_value)
        self.scroll_animation.setEndValue(target_value)
        self.scroll_animation.start()
    
    def wheelEvent(self, event):
        # Обработка скролла колесиком мыши
        scrollbar = self.scroll_area.horizontalScrollBar()
        current_value = scrollbar.value()
        
        # Определяем направление прокрутки
        delta = event.angleDelta().y()
        scroll_amount = 100  # Меньше чем у стрелок для более точного контроля
        
        if delta > 0:
            # Скролл вверх = прокрутка влево
            target_value = max(0, current_value - scroll_amount)
        else:
            # Скролл вниз = прокрутка вправо
            target_value = min(scrollbar.maximum(), current_value + scroll_amount)
        
        self.scroll_animation.stop()
        self.scroll_animation.setStartValue(current_value)
        self.scroll_animation.setEndValue(target_value)
        self.scroll_animation.start()
        
        event.accept()


# ==================== MAIN WINDOW ====================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCI-инатор")
        # Стартовый размер, разрешаем свободное изменение
        self.resize(1280, 800)
        self.setMinimumSize(800, 600)
        
        # Загружаем кастомный шрифт UI
        self._load_ui_font()
        
        # Данные
        self.img_color = None
        self.base_gray = None
        self.img_w = None
        self.img_h = None
        self.grid_cols = 40
        self.grid_rows = 40
        self.cell_w = 9
        self.cell_h = 16
        self.gap_x = 0
        self.gap_y = 0
        
        self.params = WaveParams()
        self.use_extended = False
        self.custom_ramp = ""  # Кастомные символы пользователя
        self.font_map = self._enumerate_system_fonts()
        
        # Выбираем первый доступный шрифт или дефолтный
        if self.font_map:
            self.font_name = next(iter(self.font_map.keys()))
        else:
            self.font_name = "Default"
            self.font_map = {"Default": None}
            
        self.anim_font_px = 16
        self.font_pil = self._load_font(self.font_name, self.anim_font_px)
        
        self.color_stops = [(255,255,255)]*5
        self.render_bg = (0,0,0)
        self.color_inputs = []
        self.color_swatches = []
        self.bg_hex_input = None
        self.bg_swatch = None
        
        self.mode = "waves"
        self.morph_target = None
        self.audio_gain = 2.5
        self.audio_smooth = 0.8
        self.audio_level = 0.0
        self.particles = None
        
        self.t = 0.0
        self.running = False
        self.audio_stream = None
        self.second = None
        
        # PostFX Manager
        self.postfx = PostFXManager()
        
        # Скорость анимации
        self.animation_speed_percent = 100  # Скорость в процентах (100% = нормальная)
        self.base_fps = 30  # Базовая частота обновления preview
        
        # Индекс текущего таба (для анимации)
        self._current_tab_index = 0
        
        # Оптимизация производительности
        self.glyph_cache = {}  # Кэш пререндеренных символов (symbol, color) -> PIL Image
        self.max_preview_cells = 120  # Максимум символов в одном измерении для preview
        self.last_render_time = 0  # Последнее время рендера в секундах
        self.skip_frames = False  # Пропускать кадры если рендер медленный
        
        # Храним ссылки на секции режимов
        self.morph_section = None
        self.audio_section = None
        
        # Слайдеры
        self.slider_gap_x = None
        self.slider_gap_y = None
        self.slider_speed = None
        self.speed_input = None
        
        # Экспорт
        self.cb_export_format = None
        self.stepper_frames = None
        self.stepper_fps = None
        self.stepper_upscale = None
        self.stepper_width = None
        self.stepper_height = None
        self.cb_loop = None
        
        # Тема UI (может быть переназначена через настройки)
        self.ui_theme = {
            'ui_bg': '#3F3F3F',
            'ui_text': '#FFFFFF',
            'button_bg': '#FFFFFF',
            'button_text': '#000000',
            'button_border': '#FFFFFF',
            'accent': '#FFFFFF',
        }
        
        self._build_ui()
        self._apply_figma_style()
        self._sync_color_ui()  # Синхронизируем начальные цвета с UI
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(30)

        # Первичная синхронизация иконки play/pause
        self._update_play_button_icon()
        self._last_running_state = self.running

    def _on_play_toggled(self, checked: bool):
        # Источник истины — состояние кнопки
        self.running = bool(checked)
        self._update_play_button_icon()

    def _set_running(self, is_running: bool):
        if getattr(self, 'running', None) == is_running:
            return
        self.running = is_running
        self._update_play_button_icon()

    def resizeEvent(self, event):
        # Брейкпоинт для нижних кнопок: один ряд на широких окнах, два ряда на узких
        self._arrange_bottom_buttons()
        # Подгоняем ширину контейнера кнопок под ширину превью
        try:
            if hasattr(self, 'preview_box') and hasattr(self, 'buttons_container'):
                self.buttons_container.setFixedWidth(self.preview_box.width())
        except:
            pass
        super().resizeEvent(event)

    def _arrange_bottom_buttons(self):
        # Раскладывает кнопки по сетке в зависимости от ширины окна
        if not hasattr(self, 'bottom_buttons_layout'):
            return
        grid = self.bottom_buttons_layout
        # Очистка позиций (не удаляем виджеты)
        while grid.count():
            item = grid.takeAt(0)
            # ничего, просто очищаем раскладку
        width = self.width()
        wide = width >= 1400
        if wide:
            # Один ряд, 3 группы со stretch-промежутками:
            # [import, generate] —stretch— [settings, second, export] —stretch— [play]
            for c in range(0, 12):
                grid.setColumnStretch(c, 0)
            grid.addWidget(self.btn_import, 0, 0)
            grid.addWidget(self.btn_generate, 0, 1)
            # первый stretch-промежуток
            grid.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum), 0, 2)
            grid.setColumnStretch(2, 1)
            grid.addWidget(self.btn_settings, 0, 3)
            grid.addWidget(self.btn_second, 0, 4)
            grid.addWidget(self.btn_export, 0, 5)
            # второй stretch-промежуток
            grid.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum), 0, 6)
            grid.setColumnStretch(6, 1)
            grid.addWidget(self.btn_play_pause, 0, 7, Qt.AlignLeft)
        else:
            # Два ряда: как в макете для узких
            # выравниваем ширины колонок
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(2, 1)
            grid.addWidget(self.btn_import, 0, 0)
            grid.addWidget(self.btn_settings, 0, 1)
            grid.addWidget(self.btn_export, 0, 2)
            grid.addWidget(self.btn_generate, 1, 0)
            grid.addWidget(self.btn_second, 1, 1)
            grid.addWidget(self.btn_play_pause, 1, 2, Qt.AlignLeft)
            # Жёсткая привязка ширины контейнера к ширине превью во втором брейкпоинте
            try:
                if hasattr(self, 'preview_box') and hasattr(self, 'buttons_container'):
                    self.buttons_container.setFixedWidth(self.preview_box.width())
            except Exception:
                pass
        
    def closeEvent(self, event):
        # Корректное закрытие приложения
        self._stop_audio_stream()
        if self.second is not None:
            self.second.close()
        event.accept()
    
    def _load_ui_font(self):
        # Загружает кастомный шрифт для UI интерфейса
        # Ищем файлы шрифта Helvetica Neue в папке fonts/
        font_dir = os.path.join(os.path.dirname(__file__), 'fonts')
        
        # Если запущено через PyInstaller
        if getattr(sys, 'frozen', False):
            font_dir = os.path.join(sys._MEIPASS, 'fonts')
        
        # Список возможных файлов Helvetica Neue
        helvetica_files = [
            'HelveticaNeue-Medium.ttf',
            'HelveticaNeue-Regular.ttf',
            'HelveticaNeue.ttf',
            'HelveticaNeueMedium.ttf',
            'HelveticaNeueRegular.ttf',
            'helvetica-neue-medium.ttf',
            'helvetica-neue-regular.ttf',
            'HelveticaNeue-Medium.otf',
            'HelveticaNeue-Regular.otf',
        ]
        
        font_loaded = False
        if os.path.exists(font_dir):
            for font_file in helvetica_files:
                font_path = os.path.join(font_dir, font_file)
                if os.path.exists(font_path):
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        if families:
                            print(f"[OK] UI font loaded: {families[0]} from {font_file}")
                            font_loaded = True
                            break
        
        if not font_loaded:
            print("[WARNING] Helvetica Neue not found in fonts/ folder")
            print("          Using fallback font (Segoe UI / Arial)")
            print("          Download TTF from: https://fontsgeek.com/fonts/Helvetica-Neue-Regular")
        
    def _enumerate_system_fonts(self):
        # Перечисляет системные шрифты с поддержкой PyInstaller
        fm = {}
        
        # Пути к шрифтам Windows
        font_paths = [
            "C:/Windows/Fonts",
            os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts'),
        ]
        
        # Добавляем путь относительно exe если запущено через PyInstaller
        if getattr(sys, 'frozen', False):
            # Запущено через PyInstaller
            base_path = sys._MEIPASS
            font_paths.insert(0, os.path.join(base_path, 'fonts'))
        
        for font_dir in font_paths:
            if not os.path.isdir(font_dir):
                continue
            try:
                for ext in ("*.ttf", "*.ttc", "*.otf"):
                    for p in glob.glob(os.path.join(font_dir, ext)):
                        try:
                            name = os.path.splitext(os.path.basename(p))[0]
                            fm[name] = p
                        except:
                            continue
            except Exception as e:
                print(f"Ошибка при сканировании {font_dir}: {e}")
                continue
        
        # Если не нашли шрифтов - добавляем дефолтный
        if not fm:
            fm["Default"] = None
            
        return fm
        
    def _load_font(self, name, px):
        # Загружает шрифт с fallback на дефолтный
        path = self.font_map.get(name)
        
        # Пробуем загрузить по пути
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, px)
            except Exception as e:
                print(f"Не удалось загрузить шрифт {path}: {e}")
        
        # Fallback на PIL default
        try:
            return ImageFont.load_default()
        except:
            # Если и дефолтный не загрузился - создаем минимальный
            return ImageFont.load_default()
        
    def _measure_cell(self, font, ch="M"):
        if hasattr(font, "getbbox"):
            b = font.getbbox(ch)
            return max(1,b[2]-b[0]), max(1,b[3]-b[1])
        w,h = font.getsize(ch)
        return max(1,w), max(1,h)
        
    def _build_ui(self):
        # Главный layout
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 30, 20, 20)
        root.setSpacing(15)
        
        # Левая часть: Preview + кнопки
        left_layout = QVBoxLayout()
        left_layout.setSpacing(20)
        
        # Preview с скругленными углами (через контейнер с антиалиасингом)
        preview_container = RoundedPreviewContainer()
        # Адаптивный превью: уменьшаем минимальный размер и разрешаем растягиваться
        preview_container.setMinimumSize(600, 360)
        preview_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview = preview_container.preview  # Получаем ссылку на внутренний PreviewArea
        self.preview_box = preview_container      # Контейнер превью (для выравнивания кнопок)
        left_layout.addWidget(preview_container, 1)
        
        # Кнопки внизу (адаптивная сетка 2 ряда)
        bottom_btns = QGridLayout()
        bottom_btns.setHorizontalSpacing(20)
        bottom_btns.setVerticalSpacing(12)
        
        # ГРУППА 1: Импорт и Генерация паттерна
        self.btn_import = QPushButton("import\u00A0\u00A0")
        self.btn_import.setFixedSize(162, 44)
        self.btn_import.clicked.connect(self.on_load)
        try:
            icon = load_icon('import', size=20)
            if icon:
                self.btn_import.setIcon(icon)
                self.btn_import.setIconSize(QSize(22, 22))
                # place icon on the right similar to export
                self.btn_import.setLayoutDirection(Qt.RightToLeft)
        except:
            pass
        
        self.btn_generate = QPushButton("generate pattern")
        self.btn_generate.setFixedSize(162, 44)
        self.btn_generate.setObjectName("BlackButtonNoBorder")
        self.btn_generate.clicked.connect(self.on_generate_pattern)
        
        # Верхний ряд: импорт, настройки, экспорт
        bottom_btns.addWidget(self.btn_import, 0, 0)
        
        # ГРУППА 2: Настройки, Второй вьюпорт, Экспорт (по центру)
        self.btn_settings = QPushButton("settings")
        self.btn_settings.setFixedSize(162, 44)
        self.btn_settings.setObjectName("BlackButtonNoBorder")
        self.btn_settings.clicked.connect(self.on_settings)
        
        self.btn_second = QPushButton("second viewport")
        self.btn_second.setFixedSize(162, 44)
        self.btn_second.setObjectName("BlackButtonNoBorder")
        self.btn_second.clicked.connect(self.on_second_window)
        
        self.btn_export = QPushButton("export\u00A0\u00A0")
        self.btn_export.setFixedSize(162, 44)
        self.btn_export.clicked.connect(self.on_export)
        try:
            icon = load_icon('export', size=20)
            if icon:
                self.btn_export.setIcon(icon)
                self.btn_export.setIconSize(QSize(22, 22))
                # Иконка справа от текста + немного больший зазор
                self.btn_export.setLayoutDirection(Qt.RightToLeft)
        except:
            pass
        
        bottom_btns.addWidget(self.btn_settings, 0, 1)
        bottom_btns.addWidget(self.btn_export, 0, 2)
        
        # ГРУППА 3: Play/Pause (круглая кнопка)
        self.btn_play_pause = QPushButton("")
        self.btn_play_pause.setFixedSize(54, 54)
        self.btn_play_pause.setObjectName("RoundBlackButton")
        # Новая логика: кнопка-тоггл (checked = running)
        self.btn_play_pause.setCheckable(True)
        self.btn_play_pause.setChecked(False)
        self.btn_play_pause.toggled.connect(self._on_play_toggled)
        # Возвращаем классическое поведение: клик запускает/останавливает анимацию
        self.btn_play_pause.clicked.connect(self.on_start_stop)
        # Жёсткая инициализация иконок play/pause
        self._init_play_icons()
        self._update_play_button_icon()
        
        # Нижний ряд: генерация, второй вьюпорт, play
        bottom_btns.addWidget(self.btn_generate, 1, 0)
        bottom_btns.addWidget(self.btn_second, 1, 1)
        bottom_btns.addWidget(self.btn_play_pause, 1, 2, Qt.AlignLeft)
        
        # Сохраняем ссылку на контейнер кнопок и расставляем по брейкпоинтам
        self.bottom_buttons_layout = bottom_btns
        self._arrange_bottom_buttons()
        # Оборачиваем в контейнер с фиксированными отступами и растяжением по ширине превью
        buttons_container = QWidget()
        buttons_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btns_wrap = QVBoxLayout(buttons_container)
        btns_wrap.setContentsMargins(0, 0, 0, 0)
        btns_wrap.addLayout(self.bottom_buttons_layout)
        self.buttons_container = buttons_container
        # Выравниваем контейнер кнопок по левому краю и ограничиваем его шириной превью в resizeEvent
        left_layout.addWidget(buttons_container, 0, Qt.AlignLeft)
        # Первичная синхронизация ширины кнопочного контейнера с шириной превью
        try:
            if hasattr(self, 'preview_box'):
                self.buttons_container.setFixedWidth(self.preview_box.width())
        except Exception:
            pass
        root.addLayout(left_layout, 3)
        
        # Правая часть: Табы + контент (скроллируемая панель)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(0)
        
        # Новая система табов с баблами
        tab_names = ["Canvas", "Color", "Mode", "PostFX", "Export"]
        self.tab_bar = ScrollableTabBar(tab_names)
        self.tab_bar.tabChanged.connect(self.on_tab_changed)
        
        # Контейнер для выравнивания табов слева
        tab_container = QHBoxLayout()
        tab_container.setContentsMargins(0, 0, 0, 0)
        tab_container.addWidget(self.tab_bar, 0, Qt.AlignLeft)
        tab_container.addStretch()
        right_layout.addLayout(tab_container)
        
        # Отступ 15px между табами и контентом
        right_layout.addSpacing(15)

        # Оборачиваем контент табов в QScrollArea — фиксируем расстояния, при нехватке места включается вертикальный скролл
        self.tab_content = QStackedWidget()
        self.tab_content.addWidget(self._create_canvas_tab())
        self.tab_content.addWidget(self._create_color_tab())
        self.tab_content.addWidget(self._create_modes_tab())
        self.tab_content.addWidget(self._create_postfx_tab())
        self.tab_content.addWidget(self._create_export_tab())
        
        self.tab_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content_scroll.setStyleSheet("QScrollArea{background: transparent; border: none;} QScrollBar{width:0px;height:0px;background:transparent;}")
        content_scroll.setWidget(self.tab_content)
        right_layout.addWidget(content_scroll)
        # keep reference for scroll control
        self._content_scroll = content_scroll
        
        root.addLayout(right_layout, 1)
        
    def _create_canvas_tab(self):
        # Tab: Canvas
        widget = QWidget()
        widget.setStyleSheet("QWidget { background: transparent; }")
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # === SECTION: Grid ===
        grid_section, grid_layout = self._create_new_section("grid")
        
        # GROUP 1: Columns + Rows (spacing between them 10px)
        # Columns
        cols_row = QHBoxLayout()
        cols_row.setContentsMargins(0, 0, 0, 0)
        cols_label = QLabel("columns")
        cols_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.stepper_cols = NewStepperWidget(self.grid_cols, 8, 400, self, "columns")
        self.stepper_cols.valueChanged.connect(self.on_cols_changed)
        cols_row.addWidget(cols_label)
        cols_row.addStretch()
        cols_row.addWidget(self.stepper_cols)
        grid_layout.addLayout(cols_row)
        grid_layout.addSpacing(10)  # 10px between columns and rows
        
        # Rows
        rows_row = QHBoxLayout()
        rows_row.setContentsMargins(0, 0, 0, 0)
        rows_label = QLabel("rows")
        rows_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.stepper_rows = NewStepperWidget(self.grid_rows, 8, 240, self, "rows")
        self.stepper_rows.valueChanged.connect(self.on_rows_changed)
        rows_row.addWidget(rows_label)
        rows_row.addStretch()
        rows_row.addWidget(self.stepper_rows)
        grid_layout.addLayout(rows_row)
        grid_layout.addSpacing(10)  # 10px between groups
        
        # GROUP 2: X and Y spacing (spacing between them 0px, sticky)
        # X spacing
        gap_x_row = QHBoxLayout()
        gap_x_row.setContentsMargins(0, 12, 0, 12)  # Vertical paddings for compactness
        gap_x_label = QLabel("spacing X")
        gap_x_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_gap_x = CustomSlider(0.0, 24.0, float(self.gap_x))
        self.slider_gap_x.valueChanged.connect(lambda v: (setattr(self, 'gap_x', int(v)), self.update_preview()))
        gap_x_row.addWidget(gap_x_label)
        gap_x_row.addSpacing(20)
        gap_x_row.addWidget(self.slider_gap_x, 1)  # stretch factor = 1
        grid_layout.addLayout(gap_x_row)
        # No spacing - sliders visually stick together
        
        # Y spacing
        gap_y_row = QHBoxLayout()
        gap_y_row.setContentsMargins(0, 12, 0, 12)  # Vertical paddings for compactness
        gap_y_label = QLabel("spacing Y")
        gap_y_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_gap_y = CustomSlider(0.0, 24.0, float(self.gap_y))
        self.slider_gap_y.valueChanged.connect(lambda v: (setattr(self, 'gap_y', int(v)), self.update_preview()))
        gap_y_row.addWidget(gap_y_label)
        gap_y_row.addSpacing(20)
        gap_y_row.addWidget(self.slider_gap_y, 1)  # stretch factor = 1
        grid_layout.addLayout(gap_y_row)
        
        layout.addWidget(grid_section)
        
        # === SECTION: Font ===
        font_section, font_layout = self._create_new_section("font")
        
        # Dropdown font selector
        font_combo_row = QHBoxLayout()
        font_combo_row.setContentsMargins(0, 0, 0, 0)
        self.cb_font = QComboBox()
        self.cb_font.addItems(sorted(self.font_map.keys()) or ["PIL-Default"])
        self.cb_font.currentTextChanged.connect(self.on_font_changed)
        self.cb_font.setFixedHeight(44)
        self.cb_font.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cb_font.setStyleSheet("""
            QComboBox {
                background: transparent;
                color: white;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
                padding: 10px 14px;
                font-size: 16px;
            }
            QComboBox:hover {
                border: 2px solid rgba(255,255,255,0.5);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0;
                height: 0;
            }
        """)
        font_combo_row.addWidget(self.cb_font, 1)
        font_layout.addLayout(font_combo_row)
        font_layout.addSpacing(10)  # Spacing between font selection and size
        
        # Font size
        kegl_row = QHBoxLayout()
        kegl_row.setContentsMargins(0, 0, 0, 0)
        kegl_label = QLabel("font size")
        kegl_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.stepper_kegl = NewStepperWidget(self.anim_font_px, 8, 64, self, "font size")
        self.stepper_kegl.valueChanged.connect(self.on_anim_font_px_changed)
        kegl_row.addWidget(kegl_label)
        kegl_row.addStretch()
        kegl_row.addWidget(self.stepper_kegl)
        font_layout.addLayout(kegl_row)
        
        layout.addWidget(font_section)
        
        # === SECTION: Symbols ===
        symbols_section, symbols_layout = self._create_new_section("symbols")
        
        # Checkbox "extended set"
        checkbox_row = QHBoxLayout()
        checkbox_row.setContentsMargins(0, 0, 0, 0)
        self.cb_extended = CustomCheckbox("extended set")
        self.cb_extended.stateChanged.connect(self.on_ramp_changed)
        checkbox_row.addWidget(self.cb_extended)
        checkbox_row.addStretch()
        symbols_layout.addLayout(checkbox_row)
        symbols_layout.addSpacing(10)  # Spacing before input field
        
        # Input field for custom symbols (no label)
        custom_input_row = QHBoxLayout()
        custom_input_row.setContentsMargins(0, 0, 0, 0)
        self.custom_symbols_input = QLineEdit()
        self.custom_symbols_input.setPlaceholderText("e.g.: TIPIDOR")
        self.custom_symbols_input.setMaxLength(100)
        self.custom_symbols_input.setFixedHeight(40)
        self.custom_symbols_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.custom_symbols_input.textChanged.connect(self.on_custom_symbols_changed)
        self.custom_symbols_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
                padding: 12px 14px;
                color: rgba(255,255,255,1);
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QLineEdit:focus {
                border: 2px solid rgba(255,255,255,1);
            }
            QLineEdit::placeholder {
                color: rgba(76,76,76,1);
            }
        """)
        custom_input_row.addWidget(self.custom_symbols_input)
        symbols_layout.addLayout(custom_input_row)
        
        layout.addWidget(symbols_section)
        
        # === SECTION: Waves (shown for wave/morph/audioreactive) ===
        self.waves_section, waves_layout = self._create_new_section("waves")
        
        # GROUP 1: Frequencies (sticky)
        # Frequency X
        freq_x_row = QHBoxLayout()
        freq_x_row.setContentsMargins(0, 12, 0, 12)
        freq_x_label = QLabel("frequency X")
        freq_x_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_freq_x = CustomSlider(0.0, 3.0, self.params.freq_x)
        self.slider_freq_x.valueChanged.connect(lambda v: (setattr(self.params, 'freq_x', v), self.update_preview()))
        freq_x_row.addWidget(freq_x_label)
        freq_x_row.addSpacing(20)
        freq_x_row.addWidget(self.slider_freq_x, 1)
        waves_layout.addLayout(freq_x_row)
        # 0px between frequencies - sticky
        
        # Frequency Y
        freq_y_row = QHBoxLayout()
        freq_y_row.setContentsMargins(0, 12, 0, 12)
        freq_y_label = QLabel("frequency Y")
        freq_y_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_freq_y = CustomSlider(0.0, 3.0, self.params.freq_y)
        self.slider_freq_y.valueChanged.connect(lambda v: (setattr(self.params, 'freq_y', v), self.update_preview()))
        freq_y_row.addWidget(freq_y_label)
        freq_y_row.addSpacing(20)
        freq_y_row.addWidget(self.slider_freq_y, 1)
        waves_layout.addLayout(freq_y_row)
        waves_layout.addSpacing(10)  # 10px between groups
        
        # GROUP 2: Speeds (sticky)
        # Speed X
        speed_x_row = QHBoxLayout()
        speed_x_row.setContentsMargins(0, 12, 0, 12)
        speed_x_label = QLabel("speed X")
        speed_x_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_speed_x = CustomSlider(-3.0, 3.0, self.params.speed_x)
        self.slider_speed_x.valueChanged.connect(lambda v: (setattr(self.params, 'speed_x', v), self.update_preview()))
        speed_x_row.addWidget(speed_x_label)
        speed_x_row.addSpacing(20)
        speed_x_row.addWidget(self.slider_speed_x, 1)
        waves_layout.addLayout(speed_x_row)
        # 0px between speeds - sticky
        
        # Speed Y
        speed_y_row = QHBoxLayout()
        speed_y_row.setContentsMargins(0, 12, 0, 12)
        speed_y_label = QLabel("speed Y")
        speed_y_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_speed_y = CustomSlider(-3.0, 3.0, self.params.speed_y)
        self.slider_speed_y.valueChanged.connect(lambda v: (setattr(self.params, 'speed_y', v), self.update_preview()))
        speed_y_row.addWidget(speed_y_label)
        speed_y_row.addSpacing(20)
        speed_y_row.addWidget(self.slider_speed_y, 1)
        waves_layout.addLayout(speed_y_row)
        waves_layout.addSpacing(10)  # 10px between groups
        
        # GROUP 3: Individual parameters
        # Amplitude
        amp_row = QHBoxLayout()
        amp_row.setContentsMargins(0, 12, 0, 12)
        amp_label = QLabel("amplitude")
        amp_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_amp = CustomSlider(0.0, 2.0, self.params.amplitude)
        self.slider_amp.valueChanged.connect(lambda v: (setattr(self.params, 'amplitude', v), self.update_preview()))
        amp_row.addWidget(amp_label)
        amp_row.addSpacing(20)
        amp_row.addWidget(self.slider_amp, 1)
        waves_layout.addLayout(amp_row)
        # 0px between amplitude and contrast - sticky
        
        # Contrast
        contrast_row = QHBoxLayout()
        contrast_row.setContentsMargins(0, 12, 0, 12)
        contrast_label = QLabel("contrast")
        contrast_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_contrast = CustomSlider(0.5, 2.5, self.params.contrast)
        self.slider_contrast.valueChanged.connect(lambda v: (setattr(self.params, 'contrast', v), self.update_preview()))
        contrast_row.addWidget(contrast_label)
        contrast_row.addSpacing(20)
        contrast_row.addWidget(self.slider_contrast, 1)
        waves_layout.addLayout(contrast_row)
        
        layout.addWidget(self.waves_section)
        
        # === SECTION: Audio reactive (shown only for audioreactive) ===
        self.audio_reactive_section, ar_layout = self._create_new_section("audio reactive")
        # global sensitivity
        ar_row = QHBoxLayout()
        ar_row.setContentsMargins(0, 0, 0, 0)
        ar_label = QLabel("sensitivity")
        ar_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.audio_sensitivity_display = QLabel("100%")
        self.audio_sensitivity_display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.audio_sensitivity_display.setStyleSheet("color: white; font-size: 24px; font-weight: bold; background: transparent; padding-right: 20px;")
        # simple +/- buttons capsule
        ar_buttons = QWidget()
        ar_buttons.setFixedSize(93, 48)
        ar_buttons.setStyleSheet("QWidget{background: transparent; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;}")
        arb = QHBoxLayout(ar_buttons)
        arb.setContentsMargins(2,2,2,2); arb.setSpacing(0)
        btn_minus = QPushButton("-"); btn_minus.setFixedSize(44,44)
        btn_plus  = QPushButton("+"); btn_plus.setFixedSize(44,44)
        btn_minus.clicked.connect(lambda: self._change_audio_sensitivity(-1))
        btn_plus.clicked.connect(lambda: self._change_audio_sensitivity(1))
        arb.addWidget(btn_minus)
        sep = QWidget(); sep.setFixedSize(1,44)
        sep.setStyleSheet("background: white;")
        arb.addWidget(sep)
        arb.addWidget(btn_plus)
        ar_row.addWidget(ar_label); ar_row.addStretch(); ar_row.addWidget(self.audio_sensitivity_display); ar_row.addWidget(ar_buttons)
        ar_layout.addLayout(ar_row)
        ar_layout.addSpacing(10)
        # per-band sliders (placeholders)
        names = ["60 Hz","150 Hz","400 Hz","1 kHz","2.4 kHz","15 kHz"]
        for i, n in enumerate(names):
            row = QHBoxLayout(); row.setContentsMargins(0,12,0,12)
            lbl = QLabel(f"band {n}"); lbl.setStyleSheet("color: white; font-size: 16px; background: transparent;")
            sld = CustomSlider(0.0, 2.0, 1.0)
            sld.valueChanged.connect(lambda v, idx=i: self._on_ar_band_gain_changed(idx, v))
            row.addWidget(lbl); row.addSpacing(20); row.addWidget(sld,1)
            ar_layout.addLayout(row)
        self.audio_reactive_section.hide()
        layout.addWidget(self.audio_reactive_section)

        # === SECTION: AudioReactive Alt (shown only for audioreactive_alt) ===
        self.ar_alt_section, ar_alt_layout = self._create_new_section("audio overlays")
        # Preset
        preset_row = QHBoxLayout(); preset_row.setContentsMargins(0,0,0,0)
        preset_label = QLabel("preset"); preset_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.cb_preset = QComboBox(); self.cb_preset.addItems(["Chill","Rhythmic","Impact"]) 
        self.cb_preset.setFixedWidth(160)
        self.cb_preset.currentTextChanged.connect(self._on_ar_alt_preset_changed)
        preset_row.addWidget(preset_label); preset_row.addStretch(); preset_row.addWidget(self.cb_preset)
        ar_alt_layout.addLayout(preset_row)
        ar_alt_layout.addSpacing(8)
        # OpenGL preview toggle and widget
        try:
            from asciinator.utils.gl_preview import GLPreviewWidget
            ogl_row = QHBoxLayout(); ogl_row.setContentsMargins(0,0,0,0)
            ogl_label = QLabel("OpenGL preview"); ogl_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
            self.chk_gl_preview = CustomCheckbox("Enable"); self.chk_gl_preview.setChecked(False)
            ogl_row.addWidget(ogl_label); ogl_row.addStretch(); ogl_row.addWidget(self.chk_gl_preview)
            ar_alt_layout.addLayout(ogl_row)
            self.gl_preview = GLPreviewWidget(self)
            self.gl_preview.setVisible(False)
            ar_alt_layout.addWidget(self.gl_preview)
            self.chk_gl_preview.stateChanged.connect(lambda s: self.gl_preview.setVisible(bool(s)))
        except Exception:
            self.gl_preview = None
        # Overlay toggles
        toggles = QHBoxLayout(); toggles.setContentsMargins(0,0,0,0)
        self.chk_outline = CustomCheckbox("Outline")
        self.chk_rays = CustomCheckbox("Rays")
        self.chk_bands = CustomCheckbox("Bands")
        self.chk_sparkles = CustomCheckbox("Sparkles")
        self.chk_echo = CustomCheckbox("Echo")
        self.chk_bg = CustomCheckbox("Background")
        # GPU Acceleration (Torch)
        self.chk_gpu = CustomCheckbox("GPU (Torch)")
        self.chk_gpu.setChecked(False)
        for w in [self.chk_outline, self.chk_rays, self.chk_bands, self.chk_sparkles, self.chk_echo, self.chk_bg, self.chk_gpu]:
            toggles.addWidget(w)
            toggles.addSpacing(16)
        toggles.addStretch()
        ar_alt_layout.addLayout(toggles)
        ar_alt_layout.addSpacing(8)
        # Slider helper with unified sizing/alignment
        def add_labeled_slider(text, minv, maxv, init):
            row = QHBoxLayout(); row.setContentsMargins(0,8,0,8)
            lbl = QLabel(text)
            lbl.setStyleSheet("color: white; font-size: 16px; background: transparent;")
            lbl.setFixedWidth(180)
            sld = CustomSlider(minv, maxv, init)
            try:
                sld.setFixedHeight(36)
            except Exception:
                pass
            row.addWidget(lbl)
            row.addWidget(sld, 1)
            ar_alt_layout.addLayout(row)
            return sld
        # Rays
        self.rays_count = add_labeled_slider("rays: count", 1, 64, 12)
        self.rays_length = add_labeled_slider("rays: max length", 5, 200, 80)
        self.rays_spread = add_labeled_slider("rays: spread°", 0, 120, 45)
        self.rays_intensity = add_labeled_slider("rays: intensity", 0.0, 5.0, 1.0)
        # Echo lines
        self.echo_lines = add_labeled_slider("echo: lines", 0, 12, 4)
        self.echo_spacing = add_labeled_slider("echo: spacing", 2.0, 40.0, 10.0)
        self.echo_band = add_labeled_slider("echo: band width", 1.0, 12.0, 3.0)
        # Bands
        self.bands_step = add_labeled_slider("bands: step px", 2, 24, 8)
        self.bands_thickness = add_labeled_slider("bands: thickness", 1, 12, 3)
        self.bands_speed = add_labeled_slider("bands: speed", 0, 5, 1)
        # Outline
        self.outline_width = add_labeled_slider("outline: width", 1, 6, 2)
        self.outline_intensity = add_labeled_slider("outline: intensity", 0, 1, 0.6)
        # Sparkles
        self.sparkles_density = add_labeled_slider("sparkles: density", 0, 1, 0.3)
        self.sparkles_speed = add_labeled_slider("sparkles: speed", 0, 5, 1)
        self.sparkles_gain = add_labeled_slider("sparkles: gain", 0.0, 10.0, 3.0)
        # Background
        self.bg_intensity = add_labeled_slider("background: intensity", 0.0, 2.0, 0.5)
        self.bg_speed = add_labeled_slider("background: speed", 0.0, 5.0, 1.0)
        ar_alt_layout.addSpacing(8)
        # Audio controls (global)
        self.ar_alt_sens = add_labeled_slider("audio: sensitivity", 0, 2, 1)
        # per-band mini sliders
        band_box = QVBoxLayout(); band_box.setContentsMargins(0,0,0,0)
        band_title = QLabel("audio: per-band"); band_title.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        band_box.addWidget(band_title)
        for i, n in enumerate(["60","150","400","1k","2.4k","15k"]):
            row = QHBoxLayout(); row.setContentsMargins(0,4,0,4)
            lbl = QLabel(n); lbl.setStyleSheet("color: white; background: transparent;")
            s = CustomSlider(0.0, 2.0, 1.0)
            s.valueChanged.connect(lambda v, idx=i: self._on_ar_band_gain_changed(idx, v))
            row.addWidget(lbl); row.addSpacing(12); row.addWidget(s,1)
            band_box.addLayout(row)
        ar_alt_layout.addLayout(band_box)
        # Attack/Release/Noise Gate/Beat boost/Motion-Budget
        self.ar_alt_attack = add_labeled_slider("audio: attack (ms)", 1, 100, 15)
        self.ar_alt_release = add_labeled_slider("audio: release (ms)", 20, 400, 180)
        self.ar_alt_gate = add_labeled_slider("audio: noise gate (dB)", -80, -10, -40)
        self.ar_alt_beat = add_labeled_slider("audio: beat boost", 0, 2, 0.6)
        self.ar_alt_mb = add_labeled_slider("audio: motion-budget range", 0.4, 1.8, 1.2)
        # Quality
        self.ar_alt_max_points = add_labeled_slider("quality: max points per contour", 50, 1500, 400)
        self.ar_alt_df_step = add_labeled_slider("quality: downsample dist field (px)", 1, 8, 3)
        self.ar_alt_section.hide()
        layout.addWidget(self.ar_alt_section)
        
        # === SECTION: Contourswim parameters (only for contourswim) ===
        self.contour_section, contour_layout = self._create_new_section("contourswim params")
        contour_layout.setSpacing(0)
        
        # 1. Edge sensitivity
        edge_sens_row = QHBoxLayout()
        edge_sens_row.setContentsMargins(0, 12, 0, 12)
        edge_sens_label = QLabel("edge sensitivity")
        edge_sens_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.slider_edge_sensitivity = CustomSlider(0.0, 100.0, 30.0)
        self.slider_edge_sensitivity.valueChanged.connect(lambda v: setattr(self, 'contour_edge_sensitivity', v))
        
        edge_sens_row.addWidget(edge_sens_label)
        edge_sens_row.addSpacing(20)
        edge_sens_row.addWidget(self.slider_edge_sensitivity, 1)
        contour_layout.addLayout(edge_sens_row)
        contour_layout.addSpacing(10)
        
        # 2. Wave speed
        wave_speed_row = QHBoxLayout()
        wave_speed_row.setContentsMargins(0, 12, 0, 12)
        wave_speed_label = QLabel("wave speed")
        wave_speed_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.slider_wave_speed = CustomSlider(0.0, 200.0, 100.0)
        self.slider_wave_speed.valueChanged.connect(lambda v: setattr(self, 'contour_wave_speed', v))
        
        wave_speed_row.addWidget(wave_speed_label)
        wave_speed_row.addSpacing(20)
        wave_speed_row.addWidget(self.slider_wave_speed, 1)
        contour_layout.addLayout(wave_speed_row)
        contour_layout.addSpacing(10)
        
        # 3. Amplitude of oscillations
        amplitude_row = QHBoxLayout()
        amplitude_row.setContentsMargins(0, 12, 0, 12)
        amplitude_label = QLabel("oscillation amplitude")
        amplitude_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.slider_contour_amplitude = CustomSlider(0.0, 100.0, 50.0)
        self.slider_contour_amplitude.valueChanged.connect(lambda v: setattr(self, 'contour_amplitude', v))
        
        amplitude_row.addWidget(amplitude_label)
        amplitude_row.addSpacing(20)
        amplitude_row.addWidget(self.slider_contour_amplitude, 1)
        contour_layout.addLayout(amplitude_row)
        contour_layout.addSpacing(10)
        
        # 4. Number of layers
        layers_row = QHBoxLayout()
        layers_row.setContentsMargins(0, 0, 0, 0)
        layers_label = QLabel("layers")
        layers_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.stepper_layers = NewStepperWidget(3, 1, 5, self, "number of layers")
        self.stepper_layers.valueChanged.connect(lambda v: setattr(self, 'contour_layers', v))
        
        layers_row.addWidget(layers_label)
        layers_row.addStretch()
        layers_row.addWidget(self.stepper_layers)
        contour_layout.addLayout(layers_row)
        contour_layout.addSpacing(10)
        
        # 5. Edge blur
        blur_row = QHBoxLayout()
        blur_row.setContentsMargins(0, 12, 0, 12)
        blur_label = QLabel("edge blur")
        blur_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.slider_edge_blur = CustomSlider(0.0, 100.0, 0.0)
        self.slider_edge_blur.valueChanged.connect(lambda v: setattr(self, 'contour_edge_blur', v))
        
        blur_row.addWidget(blur_label)
        blur_row.addSpacing(20)
        blur_row.addWidget(self.slider_edge_blur, 1)
        contour_layout.addLayout(blur_row)
        contour_layout.addSpacing(10)
        
        # 6. Glow intensity
        glow_row = QHBoxLayout()
        glow_row.setContentsMargins(0, 12, 0, 12)
        glow_label = QLabel("glow intensity")
        glow_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.slider_contour_glow = CustomSlider(0.0, 100.0, 50.0)
        self.slider_contour_glow.valueChanged.connect(lambda v: setattr(self, 'contour_glow', v))
        
        glow_row.addWidget(glow_label)
        glow_row.addSpacing(20)
        glow_row.addWidget(self.slider_contour_glow, 1)
        contour_layout.addLayout(glow_row)
        
        layout.addWidget(self.contour_section)
        
        # By default, we hide the contourswim section
        self.contour_section.hide()
        
        layout.addStretch()
        return widget
        
    def _create_color_tab(self):
        # Tab: Color
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Одна большая секция без заголовка (padding 20px автоматически)
        container, container_layout = self._create_new_section("")
        
        # Горизонтальный layout для двух колонок
        columns_layout = QHBoxLayout()
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(20)
        
        # ========== ЛЕВАЯ КОЛОНКА: ЦВЕТ СИМВОЛОВ ==========
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # Заголовок секции
        symbols_title = QLabel("symbol colors")
        symbols_title.setStyleSheet("""
            color: rgba(66,66,66,1);
            font-size: 16px;
            background: transparent;
        """)
        left_layout.addWidget(symbols_title)
        left_layout.addSpacing(20)
        
        # 5 строк с цветами
        for i in range(1, 6):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            
            # Номер
            num_label = QLabel(str(i))
            num_label.setFixedWidth(9)
            num_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
            
            # Поле ввода HEX
            hex_input = QLineEdit("#FFFFFF")
            hex_input.setFixedSize(93, 44)
            hex_input.setMaxLength(7)
            hex_input.setStyleSheet("""
                QLineEdit {
                    background: transparent;
                    border: 2px solid rgba(255,255,255,0.3);
                    border-radius: 20px;
                    padding: 14px;
                    color: rgba(255,255,255,1);
                    font-size: 16px;
                    font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                    font-weight: 400;
                }
                QLineEdit:focus {
                    border: 2px solid rgba(255,255,255,0.6);
                }
            """)
            
            # Цветной свотч с белой обводкой
            swatch = QLabel()
            swatch.setFixedSize(44, 44)
            swatch.setStyleSheet("background: #FFFFFF; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
            swatch.setCursor(Qt.PointingHandCursor)
            hex_input.setCursor(Qt.PointingHandCursor)  # Курсор указателя для HEX-поля
            
            # Индекс для замыкания
            idx = i - 1
            
            # Обработчик изменения HEX-кода
            def make_hex_changed(index, inp, sw):
                def on_hex_change():
                    text = inp.text().strip()
                    pattern = r'^#?[0-9A-Fa-f]{6}$'
                    if re.match(pattern, text):
                        if not text.startswith('#'):
                            text = '#' + text
                        try:
                            color = QColor(text)
                            if color.isValid():
                                sw.setStyleSheet(f"background: {text}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
                                self.color_stops[index] = (color.red(), color.green(), color.blue())
                                self.update_preview(True)
                        except:
                            pass
                return on_hex_change
            
            hex_input.editingFinished.connect(make_hex_changed(idx, hex_input, swatch))
            
            # Обработчик клика по свотчу И по HEX-полю
            def make_color_picker(index, inp, sw):
                def pick():
                    color = QColorDialog.getColor(QColor(inp.text() or "#FFFFFF"), self)
                    if color.isValid():
                        hex_val = f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
                        inp.setText(hex_val)
                        sw.setStyleSheet(f"background: {hex_val}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
                        self.color_stops[index] = (color.red(), color.green(), color.blue())
                        self.update_preview(True)
                return pick
            
            picker_func = make_color_picker(idx, hex_input, swatch)
            swatch.mousePressEvent = lambda e, f=picker_func: f()
            hex_input.mousePressEvent = lambda e, f=picker_func: f()  # Клик на HEX-поле тоже открывает picker
            
            row.addWidget(num_label)
            row.addSpacing(10)
            row.addWidget(hex_input)
            row.addSpacing(10)
            row.addWidget(swatch)
            row.addStretch()
            
            self.color_inputs.append(hex_input)
            self.color_swatches.append(swatch)
            
            left_layout.addLayout(row)
            
            # Spacing between rows (10px)
            if i < 5:
                left_layout.addSpacing(10)
        
        left_layout.addStretch()
        columns_layout.addWidget(left_column, 0)
        
        # ========== ПРАВАЯ КОЛОНКА: ЦВЕТ ФОНА + КНОПКИ ==========
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Заголовок секции
        bg_title = QLabel("background color")
        bg_title.setStyleSheet("""
            color: rgba(66,66,66,1);
            font-size: 16px;
            background: transparent;
        """)
        right_layout.addWidget(bg_title)
        right_layout.addSpacing(20)
        
        # Строка с цветом фона
        bg_row = QHBoxLayout()
        bg_row.setContentsMargins(0, 0, 0, 0)
        bg_row.setSpacing(10)
        
        # Номер "1"
        bg_num_label = QLabel("1")
        bg_num_label.setFixedWidth(9)
        bg_num_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        # Поле ввода HEX
        self.bg_hex_input = QLineEdit("#000000")
        self.bg_hex_input.setFixedSize(93, 44)
        self.bg_hex_input.setMaxLength(7)
        self.bg_hex_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
                padding: 14px;
                color: rgba(255,255,255,1);
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QLineEdit:focus {
                border: 2px solid rgba(255,255,255,0.6);
            }
        """)
        
        # Свотч фона с белой обводкой
        self.bg_swatch = QLabel()
        self.bg_swatch.setFixedSize(44, 44)
        self.bg_swatch.setStyleSheet("background: #000000; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
        self.bg_swatch.setCursor(Qt.PointingHandCursor)
        self.bg_hex_input.setCursor(Qt.PointingHandCursor)  # Курсор указателя для HEX-поля
        
        # Обработчик изменения HEX-кода фона
        def on_bg_hex_change():
            text = self.bg_hex_input.text().strip()
            pattern = r'^#?[0-9A-Fa-f]{6}$'
            if re.match(pattern, text):
                if not text.startswith('#'):
                    text = '#' + text
                try:
                    color = QColor(text)
                    if color.isValid():
                        self.bg_swatch.setStyleSheet(f"background: {text}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
                        self.render_bg = (color.red(), color.green(), color.blue())
                        self.update_preview(True)
                except:
                    pass
        
        self.bg_hex_input.editingFinished.connect(on_bg_hex_change)
        
        # Обработчик клика по свотчу фона И по HEX-полю
        def pick_bg():
            color = QColorDialog.getColor(QColor(self.bg_hex_input.text() or "#000000"), self)
            if color.isValid():
                hex_val = f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
                self.bg_hex_input.setText(hex_val)
                self.bg_swatch.setStyleSheet(f"background: {hex_val}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
                self.render_bg = (color.red(), color.green(), color.blue())
                self.update_preview(True)
        
        self.bg_swatch.mousePressEvent = lambda e: pick_bg()
        self.bg_hex_input.mousePressEvent = lambda e: pick_bg()  # Клик на HEX-поле тоже открывает picker
        
        bg_row.addWidget(bg_num_label)
        bg_row.addSpacing(10)
        bg_row.addWidget(self.bg_hex_input)
        bg_row.addSpacing(10)
        bg_row.addWidget(self.bg_swatch)
        bg_row.addStretch()
        
        right_layout.addLayout(bg_row)
        right_layout.addStretch()  # Push buttons down
        
        # Кнопки внизу справа (обернуты в QHBoxLayout для прижатия к правому краю)
        btn_random_row = QHBoxLayout()
        btn_random_row.setContentsMargins(0, 0, 0, 0)
        btn_random_row.addStretch()
        
        btn_random = QPushButton("рандомная палитра")
        btn_random.setFixedSize(209, 44)
        btn_random.setCursor(Qt.PointingHandCursor)
        btn_random.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,1);
                color: rgba(0,0,0,1);
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QPushButton:hover {
                background: rgba(235,235,235,1);
            }
            QPushButton:pressed {
                background: rgba(215,215,215,1);
            }
        """)
        btn_random.clicked.connect(self.randomize_palette)
        btn_random_row.addWidget(btn_random)
        
        right_layout.addLayout(btn_random_row)
        right_layout.addSpacing(10)  # 10px between buttons
        
        # Кнопка "импорт палитры"
        btn_import_row = QHBoxLayout()
        btn_import_row.setContentsMargins(0, 0, 0, 0)
        btn_import_row.addStretch()
        
        btn_import_palette = QPushButton("import palette")
        btn_import_palette.setFixedSize(209, 44)
        btn_import_palette.setCursor(Qt.PointingHandCursor)
        btn_import_palette.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,1);
                color: rgba(0,0,0,1);
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QPushButton:hover {
                background: rgba(235,235,235,1);
            }
            QPushButton:pressed {
                background: rgba(215,215,215,1);
            }
        """)
        btn_import_palette.clicked.connect(self.import_palette)
        btn_import_row.addWidget(btn_import_palette)
        
        right_layout.addLayout(btn_import_row)
        
        columns_layout.addWidget(right_column, 1)  # 1 = растягивается
        
        # Добавляем columns_layout в контейнер
        container_layout.addLayout(columns_layout)
        
        layout.addWidget(container)
        layout.addStretch()
        
        return widget
        
    def _create_modes_tab(self):
        # Tab: Mode
        widget = QWidget()
        widget.setStyleSheet("QWidget { background: transparent; }")
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # === SECTION: Mode ===
        mode_section, mode_layout = self._create_new_section("mode")
        
        # Dropdown for mode selection
        dropdown_row = QHBoxLayout()
        dropdown_row.setContentsMargins(0, 0, 0, 0)
        
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["waves", "morph", "audioreactive", "audioreactive_alt", "contourswim"])
        self.cb_mode.setFixedHeight(44)
        self.cb_mode.setStyleSheet("""
            QComboBox {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
                padding: 14px;
                color: rgba(255,255,255,1);
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QComboBox:focus {
                border: 2px solid rgba(255,255,255,0.6);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 15px;
            }
            QComboBox QAbstractItemView {
                background: rgba(0,0,0,1);
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 10px;
                selection-background-color: rgba(255,255,255,0.2);
                color: white;
                padding: 5px;
            }
        """)
        self.cb_mode.currentTextChanged.connect(self.on_mode_changed)
        dropdown_row.addWidget(self.cb_mode)
        mode_layout.addLayout(dropdown_row)
        mode_layout.addSpacing(10)  # 10px between dropdown and content
        
        # Mode: morph
        morph_widget = QWidget()
        morph_layout = QVBoxLayout(morph_widget)
        morph_layout.setContentsMargins(0, 0, 0, 0)  # We manually control spacing
        
        # Row: morph speed (design similar to columns/rows)
        morph_row = QHBoxLayout()
        morph_row.setContentsMargins(0, 0, 0, 0)  # No paddings - container already gives 20px
        
        morph_label = QLabel("morph speed")
        morph_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        # Large number (like in columns)
        self.morph_speed_display = QLabel("100%")
        self.morph_speed_display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.morph_speed_display.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
            padding-right: 20px;
        """)
        
        # Container for buttons -/+ "pill" with common border
        morph_buttons = QWidget()
        morph_buttons.setFixedSize(93, 48)  # Increase by 4px for border
        morph_buttons.setStyleSheet("""
            QWidget {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 22px;
            }
        """)
        morph_buttons_layout = QHBoxLayout(morph_buttons)
        morph_buttons_layout.setContentsMargins(2, 2, 2, 2)  # Compensate for border
        morph_buttons_layout.setSpacing(0)
        
        btn_morph_minus = QPushButton("-")
        btn_morph_minus.setFixedSize(44, 44)
        btn_morph_minus.clicked.connect(lambda: self._change_morph_speed(-5))
        btn_morph_minus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FFFFFF;
                border: none;
                font-size: 24px;
                font-weight: normal;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border-top-left-radius: 20px;
                border-bottom-left-radius: 20px;
            }
        """)
        
        btn_morph_plus = QPushButton("+")
        btn_morph_plus.setFixedSize(44, 44)
        btn_morph_plus.clicked.connect(lambda: self._change_morph_speed(5))
        btn_morph_plus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FFFFFF;
                border: none;
                font-size: 24px;
                font-weight: normal;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border-top-right-radius: 20px;
                border-bottom-right-radius: 20px;
            }
        """)
        
        morph_buttons_layout.addWidget(btn_morph_minus)
        
        # Vertical line-separator (shorter above and below)
        separator_container = QWidget()
        separator_container.setFixedSize(1, 44)  # Height = height of buttons
        separator_container.setStyleSheet("background: transparent;")
        separator_layout = QVBoxLayout(separator_container)
        separator_layout.setContentsMargins(0, 4, 0, 4)
        separator_layout.setSpacing(0)
        
        separator_line = QWidget()
        separator_line.setStyleSheet("background: white;")
        separator_layout.addWidget(separator_line)
        
        morph_buttons_layout.addWidget(separator_container)
        
        morph_buttons_layout.addWidget(btn_morph_plus)
        
        morph_row.addWidget(morph_label)
        morph_row.addStretch()
        morph_row.addWidget(self.morph_speed_display)
        morph_row.addWidget(morph_buttons)
        morph_layout.addLayout(morph_row)
        morph_layout.addSpacing(10)  # 10px between elements
        
        # Button: import second image
        morph_btn_row = QHBoxLayout()
        morph_btn_row.setContentsMargins(0, 0, 0, 0)  # No paddings - container already gives 20px
        
        self.btn_load_morph = QPushButton("import second image")
        self.btn_load_morph.setFixedHeight(44)
        self.btn_load_morph.setCursor(Qt.PointingHandCursor)
        self.btn_load_morph.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,1);
                color: rgba(0,0,0,1);
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QPushButton:hover {
                background: rgba(235,235,235,1);
            }
            QPushButton:pressed {
                background: rgba(215,215,215,1);
            }
        """)
        self.btn_load_morph.clicked.connect(self.on_load_morph_target)
        morph_btn_row.addWidget(self.btn_load_morph)
        morph_layout.addLayout(morph_btn_row)
        morph_layout.addSpacing(10)  # 10px between elements
        
        mode_layout.addWidget(morph_widget)
        self.morph_widget = morph_widget  # Save reference
        
        # Mode: audioreactive
        audio_widget = QWidget()
        audio_layout = QVBoxLayout(audio_widget)
        audio_layout.setContentsMargins(0, 0, 0, 0)  # We manually control spacing
        
        # Row: sensitivity (design similar to columns/rows)
        audio_row = QHBoxLayout()
        audio_row.setContentsMargins(0, 0, 0, 0)  # No paddings - container already gives 20px
        
        audio_label = QLabel("sensitivity")
        audio_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        # Large number (like in columns)
        self.audio_sensitivity_display = QLabel("100%")
        self.audio_sensitivity_display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.audio_sensitivity_display.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
            padding-right: 20px;
        """)
        
        # Container for buttons -/+ "pill" with common border
        audio_buttons = QWidget()
        audio_buttons.setFixedSize(93, 48)  # Increase by 4px for border
        audio_buttons.setStyleSheet("""
            QWidget {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 22px;
            }
        """)
        audio_buttons_layout = QHBoxLayout(audio_buttons)
        audio_buttons_layout.setContentsMargins(2, 2, 2, 2)  # Compensate for border
        audio_buttons_layout.setSpacing(0)
        
        btn_audio_minus = QPushButton("-")
        btn_audio_minus.setFixedSize(44, 44)
        btn_audio_minus.clicked.connect(lambda: self._change_audio_sensitivity(-1))
        btn_audio_minus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FFFFFF;
                border: none;
                font-size: 24px;
                font-weight: normal;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border-top-left-radius: 20px;
                border-bottom-left-radius: 20px;
            }
        """)
        
        btn_audio_plus = QPushButton("+")
        btn_audio_plus.setFixedSize(44, 44)
        btn_audio_plus.clicked.connect(lambda: self._change_audio_sensitivity(1))
        btn_audio_plus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FFFFFF;
                border: none;
                font-size: 24px;
                font-weight: normal;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border-top-right-radius: 20px;
                border-bottom-right-radius: 20px;
            }
        """)
        
        audio_buttons_layout.addWidget(btn_audio_minus)
        
        # Vertical line-separator (shorter above and below)
        audio_separator_container = QWidget()
        audio_separator_container.setFixedSize(1, 44)  # Height = height of buttons
        audio_separator_container.setStyleSheet("background: transparent;")
        audio_separator_layout = QVBoxLayout(audio_separator_container)
        audio_separator_layout.setContentsMargins(0, 4, 0, 4)
        audio_separator_layout.setSpacing(0)
        
        audio_separator_line = QWidget()
        audio_separator_line.setStyleSheet("background: white;")
        audio_separator_layout.addWidget(audio_separator_line)
        
        audio_buttons_layout.addWidget(audio_separator_container)
        
        audio_buttons_layout.addWidget(btn_audio_plus)
        
        audio_row.addWidget(audio_label)
        audio_row.addStretch()
        audio_row.addWidget(self.audio_sensitivity_display)
        audio_row.addWidget(audio_buttons)
        audio_layout.addLayout(audio_row)
        audio_layout.addSpacing(10)  # 10px between elements
        
        # Button: open audio settings
        audio_btn_row = QHBoxLayout()
        audio_btn_row.setContentsMargins(0, 0, 0, 0)  # No paddings - container already gives 20px
        
        self.btn_audio_settings = QPushButton("open audio settings")
        self.btn_audio_settings.setFixedHeight(44)
        self.btn_audio_settings.setCursor(Qt.PointingHandCursor)
        self.btn_audio_settings.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,1);
                color: rgba(0,0,0,1);
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            QPushButton:hover {
                background: rgba(235,235,235,1);
            }
            QPushButton:pressed {
                background: rgba(215,215,215,1);
            }
        """)
        self.btn_audio_settings.clicked.connect(lambda: self.on_settings(tab_index=1))
        audio_btn_row.addWidget(self.btn_audio_settings)
        audio_layout.addLayout(audio_btn_row)
        
        mode_layout.addWidget(audio_widget)
        self.audio_widget = audio_widget  # Save reference
        
        # === WIDGET: contourswim mode ===
        contourswim_widget = QWidget()
        contourswim_widget.setStyleSheet("QWidget { background: transparent; }")
        contourswim_layout = QVBoxLayout(contourswim_widget)
        contourswim_layout.setContentsMargins(0, 0, 0, 0)
        contourswim_layout.setSpacing(0)
        
        # Intensity of effect
        contour_intensity_row = QHBoxLayout()
        contour_intensity_row.setContentsMargins(0, 0, 0, 0)
        
        contour_intensity_label = QLabel("contour intensity")
        contour_intensity_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        # Display percentage
        self.contour_intensity_display = QLabel("50%")
        self.contour_intensity_display.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
            padding-right: 20px;
        """)
        
        # Container for buttons "pill"
        contour_intensity_buttons = QWidget()
        contour_intensity_buttons.setFixedSize(93, 48)
        contour_intensity_buttons.setStyleSheet("""
            QWidget {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 22px;
            }
        """)
        
        contour_intensity_buttons_layout = QHBoxLayout(contour_intensity_buttons)
        contour_intensity_buttons_layout.setContentsMargins(2, 2, 2, 2)
        contour_intensity_buttons_layout.setSpacing(0)
        
        # Buttons + and -
        btn_contour_minus = QPushButton("-")
        btn_contour_minus.setFixedSize(44, 44)
        btn_contour_minus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FFFFFF;
                font-size: 24px;
                font-weight: bold;
                border: none;
                border-radius: 20px;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        btn_contour_minus.clicked.connect(lambda: self._change_contour_intensity(-10))
        
        btn_contour_plus = QPushButton("+")
        btn_contour_plus.setFixedSize(44, 44)
        btn_contour_plus.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FFFFFF;
                font-size: 24px;
                font-weight: bold;
                border: none;
                border-radius: 20px;
                padding-top: 0px;
                padding-bottom: 4px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        btn_contour_plus.clicked.connect(lambda: self._change_contour_intensity(10))
        
        contour_intensity_buttons_layout.addWidget(btn_contour_minus)
        
        # Vertical line-separator
        contour_separator_container = QWidget()
        contour_separator_container.setFixedSize(1, 44)
        contour_separator_container.setStyleSheet("background: transparent;")
        contour_separator_layout = QVBoxLayout(contour_separator_container)
        contour_separator_layout.setContentsMargins(0, 4, 0, 4)
        contour_separator_layout.setSpacing(0)
        
        contour_separator_line = QWidget()
        contour_separator_line.setStyleSheet("background: white;")
        contour_separator_layout.addWidget(contour_separator_line)
        
        contour_intensity_buttons_layout.addWidget(contour_separator_container)
        contour_intensity_buttons_layout.addWidget(btn_contour_plus)
        
        contour_intensity_row.addWidget(contour_intensity_label)
        contour_intensity_row.addStretch()
        contour_intensity_row.addWidget(self.contour_intensity_display)
        contour_intensity_row.addWidget(contour_intensity_buttons)
        contourswim_layout.addLayout(contour_intensity_row)
        contourswim_layout.addSpacing(10)
        
        mode_layout.addWidget(contourswim_widget)
        self.contourswim_widget = contourswim_widget
        
        # Hide all modes by default
        self.morph_widget.hide()
        self.audio_widget.hide()
        self.contourswim_widget.hide()
        
        layout.addWidget(mode_section)
        layout.addStretch()
        
        # Initialize default values
        self.morph_speed = 100  # 100%
        self.contour_intensity = 50  # 50%
        
        # Contourswim parameters
        self.contour_edge_sensitivity = 30.0
        self.contour_wave_speed = 100.0
        self.contour_amplitude = 50.0
        self.contour_layers = 3
        self.contour_edge_blur = 0.0
        self.contour_glow = 50.0
        
        # Synchronize audio_sensitivity_display with audio_gain
        initial_audio_percent = int((self.audio_gain / 20.0) * 200)
        self.audio_sensitivity_display.setText(f"{initial_audio_percent}%")
        
        return widget
        
    def _create_postfx_tab(self):
        # Tab: PostFX
        widget = QWidget()
        widget.setStyleSheet("QWidget { background: transparent; }")
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)  # 10px between sections
        
        # === SECTION: CRT Monitor ===
        crt_section, crt_layout = self._create_new_section("crt monitor")
        
        # Row: checkbox "crt monitor effect" right
        crt_effect_row = QHBoxLayout()
        crt_effect_row.setContentsMargins(0, 0, 0, 0)
        
        crt_label = QLabel("crt monitor effect")
        crt_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.cb_crt_enabled = CustomCheckbox("")
        self.cb_crt_enabled.setChecked(self.postfx.crt_enabled)
        self.cb_crt_enabled.stateChanged.connect(self.on_crt_enabled_changed)
        
        crt_effect_row.addWidget(crt_label)
        crt_effect_row.addStretch()
        crt_effect_row.addWidget(self.cb_crt_enabled)
        crt_layout.addLayout(crt_effect_row)
        crt_layout.addSpacing(10)  # 10px between checkbox and sliders
        
        # Sliders CRT with 10px spacing between them
        # Scanlines
        scanlines_row = QHBoxLayout()
        scanlines_row.setContentsMargins(0, 12, 0, 12)  # Vertical paddings for sliders
        scanlines_label = QLabel("scanlines")
        scanlines_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_crt_scanlines = CustomSlider(0.0, 1.0, self.postfx.crt_scanlines)
        self.slider_crt_scanlines.valueChanged.connect(lambda v: (setattr(self.postfx, 'crt_scanlines', v), self.update_preview()))
        scanlines_row.addWidget(scanlines_label)
        scanlines_row.addSpacing(20)
        scanlines_row.addWidget(self.slider_crt_scanlines, 1)
        crt_layout.addLayout(scanlines_row)
        
        # Vignette
        vignette_row = QHBoxLayout()
        vignette_row.setContentsMargins(0, 12, 0, 12)
        vignette_label = QLabel("vignette")
        vignette_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_crt_vignette = CustomSlider(0.0, 1.0, self.postfx.crt_vignette)
        self.slider_crt_vignette.valueChanged.connect(lambda v: (setattr(self.postfx, 'crt_vignette', v), self.update_preview()))
        vignette_row.addWidget(vignette_label)
        vignette_row.addSpacing(20)
        vignette_row.addWidget(self.slider_crt_vignette, 1)
        crt_layout.addLayout(vignette_row)
        
        # RGB shift
        rgb_row = QHBoxLayout()
        rgb_row.setContentsMargins(0, 12, 0, 12)
        rgb_label = QLabel("RGB shift")
        rgb_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_crt_rgb_shift = CustomSlider(0.0, 1.0, self.postfx.crt_rgb_shift)
        self.slider_crt_rgb_shift.valueChanged.connect(lambda v: (setattr(self.postfx, 'crt_rgb_shift', v), self.update_preview()))
        rgb_row.addWidget(rgb_label)
        rgb_row.addSpacing(20)
        rgb_row.addWidget(self.slider_crt_rgb_shift, 1)
        crt_layout.addLayout(rgb_row)
        
        # Shake
        shake_row = QHBoxLayout()
        shake_row.setContentsMargins(0, 12, 0, 12)
        shake_label = QLabel("shake")
        shake_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_crt_shake = CustomSlider(0.0, 3.0, self.postfx.crt_shake)
        self.slider_crt_shake.valueChanged.connect(lambda v: setattr(self.postfx, 'crt_shake', v))
        shake_row.addWidget(shake_label)
        shake_row.addSpacing(20)
        shake_row.addWidget(self.slider_crt_shake, 1)
        crt_layout.addLayout(shake_row)
        
        layout.addWidget(crt_section)
        
        # === SECTION: Glow ===
        glow_section, glow_layout = self._create_new_section("glow")
        
        # Row: checkbox "glow effect" right
        glow_effect_row = QHBoxLayout()
        glow_effect_row.setContentsMargins(0, 0, 0, 0)
        
        glow_label = QLabel("glow effect")
        glow_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.cb_glow_enabled = CustomCheckbox("")
        self.cb_glow_enabled.setChecked(self.postfx.glow_enabled)
        self.cb_glow_enabled.stateChanged.connect(self.on_glow_enabled_changed)
        
        glow_effect_row.addWidget(glow_label)
        glow_effect_row.addStretch()
        glow_effect_row.addWidget(self.cb_glow_enabled)
        glow_layout.addLayout(glow_effect_row)
        glow_layout.addSpacing(10)  # 10px between checkbox and sliders
        
        # Intensity
        intensity_row = QHBoxLayout()
        intensity_row.setContentsMargins(0, 12, 0, 12)
        intensity_label = QLabel("intensity")
        intensity_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_glow_intensity = CustomSlider(0.0, 2.0, self.postfx.glow_intensity)
        self.slider_glow_intensity.valueChanged.connect(lambda v: (setattr(self.postfx, 'glow_intensity', v), self.update_preview()))
        intensity_row.addWidget(intensity_label)
        intensity_row.addSpacing(20)
        intensity_row.addWidget(self.slider_glow_intensity, 1)
        glow_layout.addLayout(intensity_row)
        
        # Radius
        radius_row = QHBoxLayout()
        radius_row.setContentsMargins(0, 12, 0, 12)
        radius_label = QLabel("radius")
        radius_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_glow_radius = CustomSlider(5.0, 50.0, float(self.postfx.glow_radius))
        self.slider_glow_radius.valueChanged.connect(lambda v: (setattr(self.postfx, 'glow_radius', int(v)), self.update_preview()))
        radius_row.addWidget(radius_label)
        radius_row.addSpacing(20)
        radius_row.addWidget(self.slider_glow_radius, 1)
        glow_layout.addLayout(radius_row)
        
        # Bloom
        bloom_row = QHBoxLayout()
        bloom_row.setContentsMargins(0, 12, 0, 12)
        bloom_label = QLabel("bloom")
        bloom_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.slider_glow_bloom = CustomSlider(0.0, 1.0, self.postfx.glow_bloom)
        self.slider_glow_bloom.valueChanged.connect(lambda v: (setattr(self.postfx, 'glow_bloom', v), self.update_preview()))
        bloom_row.addWidget(bloom_label)
        bloom_row.addSpacing(20)
        bloom_row.addWidget(self.slider_glow_bloom, 1)
        glow_layout.addLayout(bloom_row)
        
        layout.addWidget(glow_section)
        
        # === SECTION: Viewport Quality ===
        quality_section, quality_layout = self._create_new_section("viewport quality")
        quality_layout.setSpacing(0)  # We manually control spacing
        
        # Radio button "accurate"
        accurate_row = QHBoxLayout()
        accurate_row.setContentsMargins(0, 0, 0, 0)
        
        accurate_label = QLabel("accurate")
        accurate_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.cb_accurate_preview = CustomCheckbox("")
        self.cb_accurate_preview.setChecked(self.postfx.accurate_preview)
        self.cb_accurate_preview.stateChanged.connect(self.on_accurate_preview_changed)
        
        accurate_row.addWidget(accurate_label)
        accurate_row.addStretch()
        accurate_row.addWidget(self.cb_accurate_preview)
        quality_layout.addLayout(accurate_row)
        
        # Description for accurate (small text)
        accurate_desc = QLabel("frame rate when accurate is selected can drop to 2-3 fps,\nif a large number of characters is used")
        accurate_desc.setStyleSheet("color: white; font-size: 12px; background: transparent; margin-top: 4px;")
        accurate_desc.setWordWrap(True)
        quality_layout.addWidget(accurate_desc)
        quality_layout.addSpacing(10)  # 10px between elements
        
        # Radio button "fast"
        fast_row = QHBoxLayout()
        fast_row.setContentsMargins(0, 0, 0, 0)
        
        fast_label = QLabel("fast")
        fast_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.cb_gpu_preview = CustomCheckbox("")
        self.cb_gpu_preview.setChecked(self.postfx.use_gpu_preview)
        self.cb_gpu_preview.stateChanged.connect(lambda s: (setattr(self.postfx, 'use_gpu_preview', bool(s)), self.update_preview()))
        
        fast_row.addWidget(fast_label)
        fast_row.addStretch()
        fast_row.addWidget(self.cb_gpu_preview)
        quality_layout.addLayout(fast_row)
        
        # Description for fast (small text)
        fast_desc = QLabel("this is currently a useless feature")
        fast_desc.setStyleSheet("color: white; font-size: 12px; background: transparent; margin-top: 4px;")
        fast_desc.setWordWrap(True)
        quality_layout.addWidget(fast_desc)
        
        layout.addWidget(quality_section)
        
        layout.addStretch()
        return widget
        
    def _create_export_tab(self):
        # Tab: Export
        widget = QWidget()
        widget.setStyleSheet("QWidget { background: transparent; }")
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)  # 10px between sections
        
        # === ONE SECTION without header ===
        export_section, export_layout = self._create_new_section("")
        export_layout.setSpacing(0)  # We manually control spacing
        
        # Format (combobox)
        format_row = QHBoxLayout()
        format_row.setContentsMargins(0, 0, 0, 0)
        format_label = QLabel("format")
        format_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.cb_export_format = QComboBox()
        self.cb_export_format.addItems(["gif", "mp4"])
        self.cb_export_format.currentTextChanged.connect(self.on_export_format_changed)
        self.cb_export_format.setFixedHeight(44)
        self.cb_export_format.setStyleSheet("""
            QComboBox {
                background: transparent;
                color: white;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 20px;
                padding: 10px 14px;
                font-size: 16px;
            }
            QComboBox:hover {
                border: 2px solid rgba(255,255,255,0.5);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0;
                height: 0;
            }
        """)
        
        format_row.addWidget(format_label)
        format_row.addStretch()
        format_row.addWidget(self.cb_export_format, 0, Qt.AlignRight)
        export_layout.addLayout(format_row)
        export_layout.addSpacing(10)  # 10px between elements
        
        # Number of frames (number + pill)
        frames_row = QHBoxLayout()
        frames_row.setContentsMargins(0, 0, 0, 0)
        frames_label = QLabel("number of frames")
        frames_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.stepper_frames = NewStepperWidget(120, 2, 600, self, "number of frames")
        frames_row.addWidget(frames_label)
        frames_row.addStretch()
        frames_row.addWidget(self.stepper_frames)
        export_layout.addLayout(frames_row)
        export_layout.addSpacing(10)
        
        # FPS (number + pill)
        fps_row = QHBoxLayout()
        fps_row.setContentsMargins(0, 0, 0, 0)
        fps_label = QLabel("fps")
        fps_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        # Calculate FPS from percentage: base_fps * (percent / 100)
        initial_fps = int(self.base_fps * (self.animation_speed_percent / 100.0))
        self.stepper_fps = NewStepperWidget(initial_fps, 1, 300, self, "fps")
        self.stepper_fps.valueChanged.connect(self.on_export_fps_changed)
        fps_row.addWidget(fps_label)
        fps_row.addStretch()
        fps_row.addWidget(self.stepper_fps)
        export_layout.addLayout(fps_row)
        export_layout.addSpacing(10)
        
        # Width (number + pill)
        width_row = QHBoxLayout()
        width_row.setContentsMargins(0, 0, 0, 0)
        width_label = QLabel("width")
        width_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.stepper_width = NewStepperWidget(512, 100, 10000, self, "width")
        width_row.addWidget(width_label)
        width_row.addStretch()
        width_row.addWidget(self.stepper_width)
        export_layout.addLayout(width_row)
        export_layout.addSpacing(10)
        
        # Height (number + pill)
        height_row = QHBoxLayout()
        height_row.setContentsMargins(0, 0, 0, 0)
        height_label = QLabel("height")
        height_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.stepper_height = NewStepperWidget(512, 100, 10000, self, "height")
        height_row.addWidget(height_label)
        height_row.addStretch()
        height_row.addWidget(self.stepper_height)
        export_layout.addLayout(height_row)
        export_layout.addSpacing(10)
        
        # Animation speed (percentage + slider)
        speed_row = QHBoxLayout()
        speed_row.setContentsMargins(0, 12, 0, 12)  # Vertical paddings similar to sliders
        speed_label = QLabel("animation speed")
        speed_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        # Bold text to the left of the slider
        self.export_speed_display = QLabel("100%")
        self.export_speed_display.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
            padding-right: 20px;
        """)
        
        self.slider_export_speed = CustomSlider(10.0, 1000.0, float(self.animation_speed_percent))
        self.slider_export_speed.valueChanged.connect(lambda v: (
            self.export_speed_display.setText(f"{int(v)}%"),
            setattr(self, 'animation_speed_percent', int(v))
        ))
        
        speed_row.addWidget(speed_label)
        speed_row.addStretch()
        speed_row.addWidget(self.export_speed_display)
        speed_row.addWidget(self.slider_export_speed, 1)
        export_layout.addLayout(speed_row)
        export_layout.addSpacing(10)
        
        # Loop (checkbox to the right)
        loop_row = QHBoxLayout()
        loop_row.setContentsMargins(0, 0, 0, 0)
        loop_label = QLabel("loop")
        loop_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        
        self.cb_loop = CustomCheckbox("")
        self.cb_loop.setChecked(True)
        
        loop_row.addWidget(loop_label)
        loop_row.addStretch()
        loop_row.addWidget(self.cb_loop)
        export_layout.addLayout(loop_row)
        # Use GL preview frames for export (best effort)
        gl_row = QHBoxLayout(); gl_row.setContentsMargins(0, 0, 0, 0)
        gl_label = QLabel("use OpenGL preview frames")
        gl_label.setStyleSheet("color: white; font-size: 16px; background: transparent;")
        self.chk_export_gl = CustomCheckbox("")
        self.chk_export_gl.setChecked(False)
        gl_row.addWidget(gl_label)
        gl_row.addStretch()
        gl_row.addWidget(self.chk_export_gl)
        export_layout.addLayout(gl_row)
        
        layout.addWidget(export_section)
        
        layout.addStretch()
        return widget
        
    def on_export_format_changed(self, fmt):
        # Обработчик смены формата экспорта
        is_gif = fmt == "gif"
        self.cb_loop.setEnabled(is_gif)
        
    def _create_new_section(self, title):
        # Создает секцию в стиле редизайна: черный фон, серый заголовок
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background: rgba(0,0,0,1);
                border-radius: 30px;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)  # Управляем spacing вручную
        
        # Заголовок серым цветом (только если заголовок не пустой)
        if title:
            title_container = QHBoxLayout()
            title_container.setContentsMargins(0, 0, 0, 0)
            
            title_label = QLabel(title)
            title_label.setStyleSheet("""
                QLabel {
                    color: rgba(66,66,66,1);
                    font-size: 16px;
                    font-weight: regular;
                    background: transparent;
                }
            """)
            title_container.addWidget(title_label)
            title_container.addStretch()
            
            layout.addLayout(title_container)
            layout.addSpacing(20)  # 20px between title and content
        
        return container, layout
        
    def _create_section(self, title):
        # Создает секцию с заголовком и черным фоном (старая версия)
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(20, 30, 20, 30)
        layout.setSpacing(10)
        
        # Заголовок
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)
        
        return group
        
    def _create_slider_row(self, label_text, minimum, maximum, value):
        # Создает строку: label + слайдер
        row = QHBoxLayout()
        row.setSpacing(53)
        
        label = QLabel(label_text)
        slider = CustomSlider(minimum, maximum, value)
        
        row.addWidget(label)
        row.addWidget(slider)
        row.addStretch()
        
        return (row, slider)
        
    def _apply_figma_style(self):
        # Применяет стили из Figma дизайна
        t = self.ui_theme
        css = """
            * {
                font-family: 'Helvetica Neue', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
                font-weight: 400;
            }
            
            QWidget {
                background: __UI_BG__;
                color: __UI_TEXT__;
            }
            
            /* Табы */
            QTabWidget::pane {
                border: none;
                background: #000000;
                border-radius: 30px;
                padding: 0px;
                margin-top: 0px;
            }
            
            QTabBar {
                background: transparent;
            }
            
            QTabBar::tab {
                background: #000000;
                color: __UI_TEXT__;
                padding: 13px 22px;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                font-size: 20px;
                font-weight: 500;
                margin-right: 0px;
                min-width: 80px;
            }
            
            QTabBar::tab:selected {
                background: #000000;
                color: __UI_TEXT__;
            }
            
            QTabBar::tab:!selected {
                background: #000000;
                color: rgba(255,255,255,0.4);
            }
            
            QTabBar::tab:hover:!selected {
                color: rgba(255,255,255,0.6);
            }
            
            /* Секции */
            QGroupBox {
                background: #000000;
                border: none;
                border-radius: 20px;
                padding: 20px;
                margin-top: 10px;
            }
            
            QGroupBox QLabel#SectionTitle {
                font-size: 16px;
                font-weight: 300;
                color: __UI_TEXT__;
                background: transparent;
            }
            
            /* Лейблы */
            QLabel {
                font-size: 16px;
                color: __UI_TEXT__;
                background: transparent;
            }
            
            /* Числа в степперах */
            NumberDisplay {
                background: #000000;
                border: 2px solid __BTN_BORDER__;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
                color: __UI_TEXT__;
            }
            
            NumberDisplay:hover {
                background: #1A1A1A;
                cursor: text;
            }
            
            /* Кнопки -/+ */
            RoundButton {
                background: #000000;
                border: 1px solid __BTN_BORDER__;
                border-radius: 20px;
                color: __UI_TEXT__;
                font-size: 20px;
            }
            
            RoundButton:hover {
                background: #1A1A1A;
            }
            
            /* Комбобокс */
            QComboBox {
                background: #000000;
                border: 2px solid __BTN_BORDER__;
                border-radius: 20px;
                padding: 12px 14px;
                font-size: 16px;
                color: __UI_TEXT__;
            }
            
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid __UI_TEXT__;
                margin-right: 10px;
            }
            
            /* Чекбоксы */
            QCheckBox {
                spacing: 8px;
                font-size: 16px;
                color: __UI_TEXT__;
            }
            
            QCheckBox::indicator {
                width: 23px;
                height: 23px;
                background: transparent;
                border: 2px solid __BTN_BORDER__;
                border-radius: 8px;
            }
            
            QCheckBox::indicator:checked {
                background: __BTN_BG__;
            }
            
            /* Кнопки (основные) */
            QPushButton {
                background: __BTN_BG__;
                color: __BTN_TEXT__;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-weight: 400;
                padding: 12px;
            }
            
            QPushButton:hover {
                background: #EEEEEE;
            }
            
            /* Черные кнопки с обводкой */
            QPushButton#BlackButton {
                background: #000000;
                color: __UI_TEXT__;
                border: 2px solid __BTN_BORDER__;
            }
            
            QPushButton#BlackButton:hover {
                background: #1A1A1A;
            }
            
            /* Черные кнопки БЕЗ обводки */
            QPushButton#BlackButtonNoBorder {
                background: #000000;
                color: __UI_TEXT__;
                border: none;
            }
            
            QPushButton#BlackButtonNoBorder:hover {
                background: #1A1A1A;
            }
            
            /* Круглые черные кнопки */
            QPushButton#RoundBlackButton {
                background: #000000;
                color: __UI_TEXT__;
                border: none;
                border-radius: 27px;
                font-size: 20px;
            }
            
            QPushButton#RoundBlackButton:hover {
                background: #1A1A1A;
            }
            
            /* Preview */
            QScrollArea {
                background: #000000;
                border: none;
                border-radius: 30px;
            }
        """
        css = (css
            .replace('__UI_BG__', t['ui_bg'])
            .replace('__UI_TEXT__', t['ui_text'])
            .replace('__BTN_BG__', t['button_bg'])
            .replace('__BTN_TEXT__', t['button_text'])
            .replace('__BTN_BORDER__', t['button_border'])
        )
        self.setStyleSheet(css)
        
        # Apply ObjectName to black buttons
        self.btn_generate.setObjectName("BlackButtonNoBorder")
        self.btn_play_pause.setObjectName("RoundBlackButton")
        self.btn_settings.setObjectName("BlackButtonNoBorder")
        self.btn_second.setObjectName("BlackButtonNoBorder")

    def get_ui_theme(self):
        # Возвращает текущую тему UI
        return self.ui_theme.copy()

    def apply_ui_theme(self, theme_dict):
        # Применяет новую тему UI и обновляет стили
        if not isinstance(theme_dict, dict):
            return
        self.ui_theme.update({k: v for k, v in theme_dict.items() if k in self.ui_theme})
        self._apply_figma_style()
        self.update()
    
    def _sync_color_ui(self):
        # Синхронизирует начальные значения color_stops с UI элементами
        # Синхронизируем 5 цветов символов
        for i in range(5):
            if i < len(self.color_inputs) and i < len(self.color_swatches):
                color = self.color_stops[i]
                hex_val = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
                self.color_inputs[i].setText(hex_val)
                self.color_swatches[i].setStyleSheet(f"background: {hex_val}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
        
        # Синхронизируем цвет фона
        if self.bg_hex_input and self.bg_swatch:
            bg_hex = f"#{self.render_bg[0]:02X}{self.render_bg[1]:02X}{self.render_bg[2]:02X}"
            self.bg_hex_input.setText(bg_hex)
            self.bg_swatch.setStyleSheet(f"background: {bg_hex}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
        
    # ==================== HANDLERS ====================
    
    def on_cols_changed(self, v):
        self.grid_cols = v
        self.rebuild_base_grid()
        
    def on_rows_changed(self, v):
        self.grid_rows = v
        self.rebuild_base_grid()
        
    def on_font_changed(self, name):
        self.font_name = name
        self.font_pil = self._load_font(self.font_name, self.anim_font_px)
        self._recalc_cell_size()
        self.glyph_cache.clear()  # Очищаем кэш при смене шрифта
        self.rebuild_base_grid()
        
    def on_anim_font_px_changed(self, px):
        self.anim_font_px = int(px)
        self.font_pil = self._load_font(self.font_name, self.anim_font_px)
        self._recalc_cell_size()
        self.glyph_cache.clear()  # Очищаем кэш при смене размера
        self.rebuild_base_grid()
    
    def _change_morph_speed(self, delta):
        # Изменяет скорость морфинга
        self.morph_speed = max(0, min(100, self.morph_speed + delta))
        self.morph_speed_display.setText(f"{self.morph_speed}%")
    
    def _change_audio_sensitivity(self, delta):
        # Изменяет чувствительность аудио (в процентах от 0 до 200%)
        # Преобразуем audio_gain (0.1-20.0) в проценты (1%-200%)
        current_percent = int((self.audio_gain / 20.0) * 200)
        new_percent = max(1, min(200, current_percent + delta))
        self.audio_gain = (new_percent / 200.0) * 20.0
        self.audio_sensitivity_display.setText(f"{new_percent}%")
    
    def _on_ar_band_gain_changed(self, band_idx, value):
        # Handle per-band gain changes for audioreactive_alt
        if not hasattr(self, '_ar_band_gains'):
            self._ar_band_gains = np.ones(6, dtype=np.float32)
        self._ar_band_gains[band_idx] = float(value)
    
    def _on_ar_alt_preset_changed(self, preset_name):
        # Apply preset parameters for audioreactive_alt
        self._apply_ar_alt_preset(preset_name)
    
    def _apply_ar_alt_preset(self, preset_name):
        # Apply preset-specific parameters
        if preset_name == "Chill":
            # Chill: slow, smooth, low intensity
            if hasattr(self, 'rays_count'): self.rays_count.setValue(8)
            if hasattr(self, 'rays_length'): self.rays_length.setValue(60)
            if hasattr(self, 'rays_spread'): self.rays_spread.setValue(30)
            if hasattr(self, 'bands_step'): self.bands_step.setValue(12)
            if hasattr(self, 'bands_thickness'): self.bands_thickness.setValue(2)
            if hasattr(self, 'bands_speed'): self.bands_speed.setValue(0.5)
            if hasattr(self, 'outline_width'): self.outline_width.setValue(1)
            if hasattr(self, 'outline_intensity'): self.outline_intensity.setValue(0.4)
            if hasattr(self, 'sparkles_density'): self.sparkles_density.setValue(0.3)
            if hasattr(self, 'sparkles_speed'): self.sparkles_speed.setValue(0.5)
        elif preset_name == "Rhythmic":
            # Rhythmic: balanced, responsive
            if hasattr(self, 'rays_count'): self.rays_count.setValue(12)
            if hasattr(self, 'rays_length'): self.rays_length.setValue(80)
            if hasattr(self, 'rays_spread'): self.rays_spread.setValue(45)
            if hasattr(self, 'bands_step'): self.bands_step.setValue(8)
            if hasattr(self, 'bands_thickness'): self.bands_thickness.setValue(3)
            if hasattr(self, 'bands_speed'): self.bands_speed.setValue(1.0)
            if hasattr(self, 'outline_width'): self.outline_width.setValue(2)
            if hasattr(self, 'outline_intensity'): self.outline_intensity.setValue(0.6)
            if hasattr(self, 'sparkles_density'): self.sparkles_density.setValue(0.6)
            if hasattr(self, 'sparkles_speed'): self.sparkles_speed.setValue(1.0)
        elif preset_name == "Impact":
            # Impact: intense, fast, high energy
            if hasattr(self, 'rays_count'): self.rays_count.setValue(20)
            if hasattr(self, 'rays_length'): self.rays_length.setValue(120)
            if hasattr(self, 'rays_spread'): self.rays_spread.setValue(60)
            if hasattr(self, 'bands_step'): self.bands_step.setValue(6)
            if hasattr(self, 'bands_thickness'): self.bands_thickness.setValue(4)
            if hasattr(self, 'bands_speed'): self.bands_speed.setValue(1.5)
            if hasattr(self, 'outline_width'): self.outline_width.setValue(3)
            if hasattr(self, 'outline_intensity'): self.outline_intensity.setValue(0.8)
            if hasattr(self, 'sparkles_density'): self.sparkles_density.setValue(1.0)
            if hasattr(self, 'sparkles_speed'): self.sparkles_speed.setValue(1.5)
    
    def _change_contour_intensity(self, delta):
        # Изменяет интенсивность контуров (в процентах от 0 до 100%)
        self.contour_intensity = max(0, min(100, self.contour_intensity + delta))
        self.contour_intensity_display.setText(f"{self.contour_intensity}%")
        
    def on_animation_speed_slider_changed(self, percent):
        # Обработчик изменения скорости через слайдер
        self._set_animation_speed(int(percent))
        # Обновляем поле ввода
        if self.speed_input:
            self.speed_input.blockSignals(True)
            self.speed_input.setText(f"{self.animation_speed_percent}%")
            self.speed_input.blockSignals(False)
    
    def on_animation_speed_input_changed(self):
        # Обработчик изменения скорости через поле ввода
        try:
            text = self.speed_input.text().strip().replace('%', '')
            speed_value = int(text)
            if speed_value < 1:
                speed_value = 1
            self._set_animation_speed(speed_value)
            # Обновляем слайдер если значение в его диапазоне
            if 10 <= speed_value <= 300:
                self.slider_speed.blockSignals(True)
                self.slider_speed.setValue(float(speed_value))
                self.slider_speed.blockSignals(False)
        except ValueError:
            # Если введено некорректное значение, восстанавливаем текущее
            self.speed_input.setText(f"{self.animation_speed_percent}%")
    
    def _set_animation_speed(self, percent):
        # Устанавливает скорость анимации в процентах
        self.animation_speed_percent = max(1, percent)
        # Синхронизируем с stepper FPS in export
        if self.stepper_fps:
            export_fps = int(self.base_fps * (self.animation_speed_percent / 100.0))
            self.stepper_fps.blockSignals(True)
            self.stepper_fps.setValue(export_fps)
            self.stepper_fps.blockSignals(False)
    
    def on_export_fps_changed(self, fps):
        # Обработчик изменения FPS из настроек экспорта (конвертируем в проценты)
        # Конвертируем FPS в проценты относительно базового FPS (30)
        percent = int((fps / 30.0) * 100)
        self._set_animation_speed(percent)
        # Синхронизируем со слайдером в настройках холста
        if self.slider_speed and 10 <= percent <= 300:
            self.slider_speed.blockSignals(True)
            self.slider_speed.setValue(float(percent))
            self.slider_speed.blockSignals(False)
        # Синхронизируем с полем ввода
        if self.speed_input:
            self.speed_input.blockSignals(True)
            self.speed_input.setText(f"{self.animation_speed_percent}%")
            self.speed_input.blockSignals(False)
        
    def on_ramp_changed(self, _):
        self.use_extended = self.cb_extended.isChecked()
        self.glyph_cache.clear()  # Очищаем кэш при смене набора символов
        self.update_preview(True)
        
    def on_crt_enabled_changed(self, state):
        # Обработчик включения CRT эффекта
        self.postfx.crt_enabled = bool(state)
        self.update_preview()
        
    def on_glow_enabled_changed(self, state):
        # Обработчик включения Glow эффекта
        self.postfx.glow_enabled = bool(state)
        self.update_preview()
        
    def on_accurate_preview_changed(self, state):
        # Обработчик переключения Accurate Preview
        self.postfx.accurate_preview = bool(state)
        
        # При включении Accurate Preview - выключаем Fast Preview
        if self.postfx.accurate_preview:
            self.postfx.use_gpu_preview = False
            self.cb_gpu_preview.setChecked(False)
            self.cb_gpu_preview.setEnabled(False)
            
            # Показываем предупреждение
            QMessageBox.information(
                self, 
                "Accurate Preview enabled",
                "Preview now shows EXACT result of export.\n\n"
                "⚠️ This is a slow mode (~10-20 FPS)\n"
                "Animation will update every 2-3 frames.\n\n"
                "It's normal! Use it for final check before exporting."
            )
        else:
            self.cb_gpu_preview.setEnabled(True)
        
        self.update_preview()
        
    def on_custom_symbols_changed(self, text):
        # Обработчик изменения кастомных символов
        self.custom_ramp = text.strip()
        
        # Если введены кастомные символы - отключаем чекбокс расширенного набора
        has_custom = len(self.custom_ramp) >= 2
        self.cb_extended.setEnabled(not has_custom)
        
        # Визуальная индикация
        if has_custom:
            self.cb_extended.setStyleSheet("color: rgba(255,255,255,0.3);")
        else:
            self.cb_extended.setStyleSheet("")  # Возвращаем стандартный стиль
        
        self.glyph_cache.clear()  # Очищаем кэш
        self.update_preview(True)
        
    def on_mode_changed(self, m):
        # Обработчик смены режима
        # Конвертируем новые названия в старые для совместимости
        mode_map = {
            "waves": "waves",
            "morph": "morphing",
            "audioreactive": "audio",
            "audioreactive_alt": "audioreactive_alt",
            "contourswim": "contourswim"
        }
        self.mode = mode_map.get(m, m)
        
        # Показываем/скрываем нужный режим
        self.morph_widget.setVisible(m == "morph")
        self.audio_widget.setVisible(m == "audioreactive")
        self.contourswim_widget.setVisible(m == "contourswim")
        
        # Переключаем секции настроек холста в зависимости от режима
        if hasattr(self, 'waves_section') and hasattr(self, 'contour_section'):
            if m == "contourswim":
                self.waves_section.hide()
                self.contour_section.show()
            elif m == "audioreactive_alt":
                self.waves_section.hide()
                self.contour_section.hide()
            else:
                self.waves_section.show()
                self.contour_section.hide()
        
        # Показываем/скрываем секции аудио
        if hasattr(self, 'audio_reactive_section'):
            self.audio_reactive_section.setVisible(m == "audioreactive")
        if hasattr(self, 'ar_alt_section'):
            self.ar_alt_section.setVisible(m == "audioreactive_alt")
        
        # Проверка sounddevice для audioreactive modes
        if (m == "audioreactive" or m == "audioreactive_alt") and sd is None:
            QMessageBox.information(self, "microphone", "Install sounddevice:\npip install sounddevice")
            
        # Управление audio stream
        if (self.mode == "audio" or self.mode == "audioreactive_alt") and self.running and sd is not None:
            self._start_audio_stream()
        else:
            self._stop_audio_stream()
        
        # Очищаем кэш при смене режима (может быть разное кол-во символов)
        self.glyph_cache.clear()
        self.update_preview(True)
        
    def on_load_morph_target(self):
        # Загрузка второго изображения для morphing
        fn, _ = QFileDialog.getOpenFileName(self, "второе изображение", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not fn:
            return
        pil = Image.open(fn).convert("RGB")
        arr = np.array(pil, dtype=np.uint8)
        gray = to_grayscale(arr)
        grid, _, _ = resize_to_char_grid(gray, self.cell_w, self.cell_h, self.grid_cols, self.grid_rows)
        self.morph_target = grid
        QMessageBox.information(self, "готово", "второе изображение загружено")
        self.update_preview(True)
        
    def on_load(self):
        fn, _ = QFileDialog.getOpenFileName(self, "выберите изображение", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not fn:
            return
        pil = Image.open(fn).convert("RGB")
        arr = np.array(pil, dtype=np.uint8)
        self.img_color = arr
        self.img_h, self.img_w = arr.shape[0], arr.shape[1]
        self._recalc_cell_size()
        gray = to_grayscale(arr)
        grid, cols, rows = resize_to_char_grid(gray, self.cell_w, self.cell_h, None, None)
        self.base_gray = grid
        # Precompute and cache full-res edges/dist for audioreactive_alt overlays
        try:
            from asciinator.core.edges import get_edge_data
            g_norm = gray.astype(np.float32) / 255.0
            edges_full, dist_full = get_edge_data((self.img_h, self.img_w, 0), g_norm.tobytes())
            self._cached_edges_full = edges_full
            self._cached_dist_full = dist_full
        except Exception:
            self._cached_edges_full = None
            self._cached_dist_full = None
        self.grid_cols, self.grid_rows = cols, rows
        self.stepper_cols.setValue(cols)
        self.stepper_rows.setValue(rows)
        if self.mode == "swarm":
            pass
        # При загрузке изображения автоматически запускаем анимацию
        self._set_running(True)
        self.update_preview(True)
        
    def on_generate_pattern(self):
        w, ok1 = QInputDialog.getInt(self, "ширина (px)", "ширина", 512, 64, 4096, 16)
        if not ok1:
            return
        h, ok2 = QInputDialog.getInt(self, "высота (px)", "высота", 512, 64, 4096, 16)
        if not ok2:
            return
        ang, ok3 = QInputDialog.getDouble(self, "угловатость (0..1)", "угловатость", 0.5, 0.0, 1.0, 2)
        if not ok3:
            return
        arr = generate_random_shapes(w, h, n=30, angularity=ang)
        self.img_color = np.stack([arr*255]*3,axis=-1).astype(np.uint8)
        self.img_h, self.img_w = h, w
        self._recalc_cell_size()
        grid, cols, rows = resize_to_char_grid(arr, self.cell_w, self.cell_h, None, None)
        self.base_gray = grid
        # Precompute and cache edges/dist for generated pattern as well
        try:
            from asciinator.core.edges import get_edge_data
            g_norm = arr.astype(np.float32)
            if g_norm.max() > 1.0:
                g_norm = g_norm / 255.0
            edges_full, dist_full = get_edge_data((h, w, 0), g_norm.tobytes())
            self._cached_edges_full = edges_full
            self._cached_dist_full = dist_full
        except Exception:
            self._cached_edges_full = None
            self._cached_dist_full = None
        self.grid_cols, self.grid_rows = cols, rows
        self.stepper_cols.setValue(cols)
        self.stepper_rows.setValue(rows)
        if self.mode == "swarm":
            pass
        # Генерация паттерна тоже стартует анимацию
        self._set_running(True)
        self.update_preview(True)
        
    def on_start_stop(self):
        # Традиционное поведение: клик меняет состояние
        self._set_running(not self.running)
        # Управление audio stream
        if self.mode == "audio" or self.mode == "audioreactive_alt":
            if self.running and sd is not None:
                self._start_audio_stream()
            else:
                self._stop_audio_stream()
                
    def _start_audio_stream(self):
        # Запуск аудио-стрима
        if sd is None or self.audio_stream is not None:
            return
            
        def audio_cb(indata, frames, time_info, status):
            if status:
                pass
            lvl = float(np.sqrt(np.mean(np.square(indata.astype(np.float32)))))
            alpha = 1.0 - self.audio_smooth
            self.audio_level = (1.0-alpha)*self.audio_level + alpha*min(1.0, lvl*5.0)
        
        try:
            self.audio_stream = sd.InputStream(
                channels=1,
                samplerate=44100,
                blocksize=2048,
                callback=audio_cb
            )
            self.audio_stream.start()
        except Exception as e:
            QMessageBox.warning(self, "error", f"Failed to open microphone:\n{e}")
            self.audio_stream = None
            
    def _stop_audio_stream(self):
        # Остановка аудио-стрима
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except:
                pass
            self.audio_stream = None
            
    def _init_particles(self):
        # Инициализация частиц для режима рой
        rows, cols = (self.base_gray.shape if self.base_gray is not None else (60, 60))
        n = max(100, cols*rows//8)
        rng = np.random.default_rng()
        x = rng.random(n)*cols
        y = rng.random(n)*rows
        vx = (rng.random(n)-0.5)*0.6
        vy = (rng.random(n)-0.5)*0.6
        self.particles = [x, y, vx, vy]
        
    def _render_particles(self, t):
        # Рендеринг режима рой
        if self.base_gray is None:
            return None
            
        rows, cols = self.base_gray.shape
        if self.particles is None:
            self._init_particles()
            
        x, y, vx, vy = self.particles
        gx, gy = np.meshgrid(np.linspace(0,1,cols), np.linspace(0,1,rows))
        flow_x = np.sin(2*math.pi*(gx*0.6 + t*0.2)) * 0.1
        flow_y = np.cos(2*math.pi*(gy*0.6 + t*0.2)) * 0.1
        
        for i in range(len(x)):
            fx = np.interp(x[i]%cols, np.arange(cols), flow_x[int(y[i])%rows])
            fy = np.interp(y[i]%rows, np.arange(rows), flow_y[:,int(x[i])%cols])
            vx[i] = 0.97*vx[i] + fx
            vy[i] = 0.97*vy[i] + fy
            x[i] = (x[i] + vx[i]) % cols
            y[i] = (y[i] + vy[i]) % rows
            
        grid = np.zeros((rows, cols), dtype=np.float32)
        xi = np.clip(x.astype(int), 0, cols-1)
        yi = np.clip(y.astype(int), 0, rows-1)
        np.add.at(grid, (yi, xi), 1.0)
        grid = grid / (grid.max()+1e-6)
        return clamp01(0.3*(1.0-self.base_gray) + 0.7*grid)
        
    def randomize_palette(self):
        # Генерирует случайную палитру
        for i in range(5):
            if random.random() < 0.25:
                g = random.randint(0, 255)
                color = (g, g, g)
            else:
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            self.color_stops[i] = color
            hex_val = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
            self.color_inputs[i].setText(hex_val)
            self.color_swatches[i].setStyleSheet(f"background: {hex_val}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
        self.glyph_cache.clear()  # Очищаем кэш при смене палитры
        self.update_preview(True)
        
    def import_palette(self):
        # Импортирует палитру из изображения
        fn, _ = QFileDialog.getOpenFileName(self, "выберите изображение для палитры", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not fn:
            return
        try:
            pil = Image.open(fn).convert("RGB")
            q = pil.quantize(colors=5, method=Image.MEDIANCUT)
            pal = q.getpalette()
            arr = np.array(q, dtype=np.uint8).ravel()
            counts = np.bincount(arr, minlength=256)
            idxs = counts.argsort()[::-1]
            
            for i, idx in enumerate(idxs[:5]):
                r = pal[idx*3+0] if idx*3+2 < len(pal) else 255
                g = pal[idx*3+1] if idx*3+2 < len(pal) else 255
                b = pal[idx*3+2] if idx*3+2 < len(pal) else 255
                color = (int(r), int(g), int(b))
                self.color_stops[i] = color
                hex_val = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
                self.color_inputs[i].setText(hex_val)
                self.color_swatches[i].setStyleSheet(f"background: {hex_val}; border: 2px solid rgba(255,255,255,0.3); border-radius: 22px;")
            self.glyph_cache.clear()  # Очищаем кэш при смене палитры
            self.update_preview(True)
        except Exception as e:
            QMessageBox.critical(self, "error", f"Failed to extract palette:\n{e}")
        
    def on_export(self):
        if self.base_gray is None:
            QMessageBox.warning(self, "нет изображения", "сначала загрузите изображение.")
            return
            
        fmt = self.cb_export_format.currentText().upper()
        
        # Проверяем доступность ffmpeg для MP4
        if fmt == "MP4":
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                if not os.path.exists(ffmpeg_exe):
                    QMessageBox.warning(
                        self, 
                        "ffmpeg not found",
                        "For MP4 export, ffmpeg is required.\n\nInstall: pip install imageio-ffmpeg"
                    )
                    return
            except Exception as e:
                QMessageBox.warning(
                    self, 
                    "ffmpeg not available",
                    f"Failed to find ffmpeg:\n{e}\n\nInstall: pip install imageio-ffmpeg"
                )
                return
        
        if fmt == "GIF":
            fn, _ = QFileDialog.getSaveFileName(self, "сохранить gif", "ascii.gif", "GIF (*.gif)")
        else:
            fn, _ = QFileDialog.getSaveFileName(self, "сохранить mp4", "ascii.mp4", "MP4 (*.mp4)")
            
        if not fn:
            return
            
        # Проверяем путь на кириллицу (проблема с ffmpeg)
        if fmt == "MP4":
            try:
                fn.encode('ascii')
            except UnicodeEncodeError:
                reply = QMessageBox.question(
                    self,
                    "Путь содержит не-ASCII символы",
                    "Путь к файлу содержит кириллицу или специальные символы.\n"
                    "FFmpeg может работать нестабильно.\n\n"
                    "Рекомендуется выбрать путь с английскими буквами.\n\n"
                    "Продолжить всё равно?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            
        # Получаем параметры из UI (с безопасными значениями по умолчанию)
        frames = self.stepper_frames.value() if getattr(self, 'stepper_frames', None) else 120
        fps = self.stepper_fps.value() if getattr(self, 'stepper_fps', None) else 30
        upscale = (self.stepper_upscale.value() / 100.0) if getattr(self, 'stepper_upscale', None) else 1.0
        target_w = self.stepper_width.value() if getattr(self, 'stepper_width', None) and self.stepper_width.value() > 0 else None
        target_h = self.stepper_height.value() if getattr(self, 'stepper_height', None) and self.stepper_height.value() > 0 else None
        loop = self.cb_loop.isChecked() if getattr(self, 'cb_loop', None) else True
        crf = 20
        
        # Останавливаем анимацию
        was_running = self.running
        self._set_running(False)
        
        # Создаем диалог прогресса
        self.loader = LoaderDialog("рендер")
        worker = ExportWorker(self, fmt, fn, frames, fps, upscale, target_w, target_h, loop, crf)
        self.worker = worker
        
        self.loader.cancel_requested.connect(worker.cancel)
        worker.progress.connect(self.loader.set_progress)
        
        def on_done(path):
            self.loader.close()
            QMessageBox.information(self, "done", f"saved:\n{path}")
            self._set_running(was_running)
            
        def on_error(msg):
            self.loader.close()
            # Показываем расширенную ошибку
            error_dialog = QMessageBox(self)
            error_dialog.setIcon(QMessageBox.Critical)
            error_dialog.setWindowTitle("export error")
            error_dialog.setText("Failed to export video")
            error_dialog.setDetailedText(msg)
            error_dialog.exec()
            self._set_running(was_running)
            
        worker.done.connect(on_done)
        worker.error.connect(on_error)
        worker.start()
        self.loader.exec()
        
    def on_tab_changed(self, index):
        # Обработчик переключения табов с анимацией
        if not hasattr(self, '_current_tab_index'):
            self._current_tab_index = 0
        
        if index == self._current_tab_index:
            return
        
        # Анимация перехода
        self._animate_tab_change(self._current_tab_index, index)
        self._current_tab_index = index
        # reset scroll to top on tab change
        try:
            if hasattr(self, '_content_scroll'):
                self._content_scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass
    
    def _animate_tab_change(self, old_index, new_index):
        # Анимация слайда между табами с fade эффектом и gap
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QPoint, QVariantAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        
        # Определяем направление (влево или вправо)
        direction = 1 if new_index > old_index else -1
        
        # Получаем виджеты
        old_widget = self.tab_content.widget(old_index)
        new_widget = self.tab_content.widget(new_index)
        
        if not old_widget or not new_widget:
            self.tab_content.setCurrentIndex(new_index)
            return
        
        # Получаем ширину контейнера
        width = self.tab_content.width()
        gap = int(width * 0.3)  # 30% gap between panels
        
        # Создаем opacity эффекты для fade
        old_opacity_effect = QGraphicsOpacityEffect(old_widget)
        new_opacity_effect = QGraphicsOpacityEffect(new_widget)
        old_widget.setGraphicsEffect(old_opacity_effect)
        new_widget.setGraphicsEffect(new_opacity_effect)
        
        # Устанавливаем начальные позиции с gap
        old_widget.setGeometry(0, 0, width, self.tab_content.height())
        new_widget.setGeometry(direction * (width + gap), 0, width, self.tab_content.height())
        
        # Начальные opacity - важно установить до show()
        old_opacity_effect.setOpacity(1.0)
        new_opacity_effect.setOpacity(0.0)
        
        # Делаем оба виджета видимыми
        self.tab_content.setCurrentIndex(new_index)
        old_widget.raise_()
        new_widget.raise_()
        old_widget.show()
        new_widget.show()
        
        # Принудительно обновляем отображение
        old_widget.update()
        new_widget.update()
        
        # Создаем группу анимаций
        anim_group = QParallelAnimationGroup(self)
        
        # === Анимация для СТАРОГО виджета ===
        # Позиция (уезжает с gap)
        anim_old_pos = QPropertyAnimation(old_widget, b"pos")
        anim_old_pos.setDuration(500)
        anim_old_pos.setStartValue(QPoint(0, 0))
        anim_old_pos.setEndValue(QPoint(-direction * (width + gap), 0))
        anim_old_pos.setEasingCurve(QEasingCurve.InOutCubic)
        
        # Opacity (затухает) - делаем более заметным
        anim_old_opacity = QPropertyAnimation(old_opacity_effect, b"opacity")
        anim_old_opacity.setDuration(500)
        anim_old_opacity.setStartValue(1.0)
        anim_old_opacity.setEndValue(0.0)
        anim_old_opacity.setEasingCurve(QEasingCurve.InCubic)  # Быстрее затухает в начале
        
        # === Анимация для НОВОГО виджета ===
        # Позиция (приезжает с gap)
        anim_new_pos = QPropertyAnimation(new_widget, b"pos")
        anim_new_pos.setDuration(500)
        anim_new_pos.setStartValue(QPoint(direction * (width + gap), 0))
        anim_new_pos.setEndValue(QPoint(0, 0))
        anim_new_pos.setEasingCurve(QEasingCurve.InOutCubic)
        
        # Opacity (появляется) - делаем более заметным
        anim_new_opacity = QPropertyAnimation(new_opacity_effect, b"opacity")
        anim_new_opacity.setDuration(500)
        anim_new_opacity.setStartValue(0.0)
        anim_new_opacity.setEndValue(1.0)
        anim_new_opacity.setEasingCurve(QEasingCurve.OutCubic)  # Медленнее появляется в конце
        
        # Добавляем все анимации в группу
        anim_group.addAnimation(anim_old_pos)
        anim_group.addAnimation(anim_old_opacity)
        anim_group.addAnimation(anim_new_pos)
        anim_group.addAnimation(anim_new_opacity)
        
        # Обработчик обновления для принудительной перерисовки
        def on_value_changed():
            old_widget.update()
            new_widget.update()
        
        anim_old_opacity.valueChanged.connect(on_value_changed)
        anim_new_opacity.valueChanged.connect(on_value_changed)
        
        # Убираем эффекты после завершения анимации
        def cleanup():
            try:
                old_widget.setGraphicsEffect(None)
                new_widget.setGraphicsEffect(None)
            except:
                pass
        
        anim_group.finished.connect(cleanup)
        
        # Запускаем анимацию
        anim_group.start()
        
        # Сохраняем ссылки
        self._tab_animation = anim_group
        self._old_opacity_effect = old_opacity_effect
        self._new_opacity_effect = new_opacity_effect
    
    def on_settings(self, tab_index=0):
        # Открытие окна настроек
        # Args: tab_index: 0 - Интерфейс, 1 - Аудио
        
        # Create overlay for darken/blur effect
        overlay = QWidget(self)
        overlay.setStyleSheet("background: rgba(0, 0, 0, 180);")  # 70% opacity
        overlay.setGeometry(self.rect())
        overlay.show()
        
        # Apply blur effect to main window
        blur_effect = QGraphicsBlurEffect()
        blur_effect.setBlurRadius(10)
        self.setGraphicsEffect(blur_effect)
        
        # Create and show dialog
        dialog = SettingsDialog(self)
        
        # Switch to requested tab
        if hasattr(dialog, 'content_stack'):
            dialog._switch_tab(tab_index)
        
        # Execute dialog (modal)
        dialog.exec()
        
        # Remove blur and overlay after dialog closes
        self.setGraphicsEffect(None)
        overlay.deleteLater()

    def _update_play_button_icon(self):
        try:
            icon = self.icon_pause if self.running else self.icon_play
            self.btn_play_pause.setIcon(QIcon())
            if not icon.isNull():
                self.btn_play_pause.setIcon(icon)
                self.btn_play_pause.setIconSize(QSize(22, 22))
            self.btn_play_pause.update()
        except:
            pass

    def _init_play_icons(self):
        base_dir = os.path.dirname(__file__)
        project_icons = os.path.join(base_dir, 'icons')
        absolute_icons = r"C:\\Users\\mikha\\Documents\\gen16\\icons"
        search_dirs = []
        # 1) Абсолютный путь, который указал пользователь
        if os.path.isdir(absolute_icons):
            search_dirs.append(absolute_icons)
        # 2) Локальная папка проекта
        if os.path.isdir(project_icons):
            search_dirs.append(project_icons)
        def load_exact(name):
            for d in search_dirs:
                for ext in ('.svg', '.png', '.svg.svg'):
                    p = os.path.join(d, name + ext)
                    if os.path.exists(p):
                        return QIcon(p)
            return QIcon()
        self.icon_play = load_exact('play')
        self.icon_pause = load_exact('pause')
        
    def on_second_window(self):
        if self.second is None or not isinstance(self.second, FullscreenPreview):
            self.second = FullscreenPreview()
        try:
            self.second.show_on_second_screen()
        except Exception:
            self.second.show()
        if self.base_gray is not None:
            img = self.render_frame_pil()
            qimg = self.qimage_from_pil(img)
            self.second.set_image(qimg)
            
    def on_tick(self):
        # Обновляем shake эффект каждый кадр (даже если анимация на паузе)
        if self.postfx.crt_enabled and self.postfx.crt_shake > 0:
            self.postfx.update_shake()
        
        if self.running and self.base_gray is not None:
            # Используем dt основанный на базовом FPS и множитель скорости
            base_dt = 1.0 / self.base_fps  # Базовый временной шаг (1/30)
            speed_multiplier = self.animation_speed_percent / 100.0  # Множитель (100% = 1.0, 200% = 2.0)
            dt = base_dt * speed_multiplier
            self.t += dt
            
            # Пропускаем кадры если рендер медленный
            if self.skip_frames:
                import random
                if random.random() < 0.5:  # Пропускаем ~50% кадров
                    return
                    
        # В режиме Accurate Preview снижаем частоту обновления
        if self.postfx.accurate_preview:
            # Обновляем только каждый 3-й кадр в Accurate режиме
            if not hasattr(self, '_accurate_frame_count'):
                self._accurate_frame_count = 0
            self._accurate_frame_count += 1
            
            # Обновляем preview реже
            if self.postfx.crt_enabled and self.postfx.crt_shake > 0:
                # Shake требует обновления чаще
                if self._accurate_frame_count % 2 == 0:
                    self.update_preview()
            elif self.running and self.base_gray is not None:
                # Анимация - каждый 3-й кадр
                if self._accurate_frame_count % 3 == 0:
                    self.update_preview()
        else:
            # Быстрый режим - обновляем каждый кадр
            if self.postfx.crt_enabled and self.postfx.crt_shake > 0:
                self.update_preview()
            elif self.running and self.base_gray is not None:
                self.update_preview()
        # Синхронизация иконки play/pause при внешних изменениях состояния
        if getattr(self, '_last_running_state', None) != self.running:
            self._update_play_button_icon()
            self._last_running_state = self.running
            
    def _recalc_cell_size(self):
        w,h = self._measure_cell(self.font_pil, "M")
        self.cell_w = max(6, int(w))
        self.cell_h = max(10, int(h))
        
    def rebuild_base_grid(self):
        if self.img_color is None:
            return
        gray = to_grayscale(self.img_color)
        grid, cols, rows = resize_to_char_grid(gray, self.cell_w, self.cell_h, self.grid_cols, self.grid_rows)
        self.base_gray = grid
        if self.mode == "swarm":
            pass
        self.update_preview(True)
        
    def render_frame_gray(self, t):
        if self.base_gray is None:
            return None
            
            
        if self.mode == "waves":
            return apply_waves_time(self.base_gray, t, self.params)
            
        elif self.mode == "morphing":
            from asciinator.core.morph import render_morph
            return render_morph(self.base_gray, self.morph_target, t, self.params)
            
        elif self.mode == "audio":
            try:
                from asciinator.core.audio_input import AudioInput
                from asciinator.core.audio_analyzer import SixBandAnalyzer
                from asciinator.core.audio import render_audio
                if not hasattr(self, '_audio_input'):
                    self._audio_input = AudioInput(samplerate=48000, blocksize=1024, channels=1)
                    self._audio_input.start()
                if not hasattr(self, '_audio_an'):
                    self._audio_an = SixBandAnalyzer(samplerate=48000)
                samples = self._audio_input.get_latest(2048)
                bands = self._audio_an.process(samples)
                self._audio_bands = bands
                return render_audio(self.base_gray, t, self.params, bands, self.audio_gain)
            except Exception:
                from asciinator.core.audio import render_audio as _fallback
                import numpy as _np
                self._audio_bands = _np.array([self.audio_level]*6, dtype=float)
                return _fallback(self.base_gray, t, self.params, self._audio_bands, self.audio_gain)
            
        elif self.mode == "swarm":
            pass
            
        elif self.mode == "contourswim":
            try:
                from asciinator.core.contourswim import render_contourswim
                return render_contourswim(
                    self.base_gray,
                    t,
                    edge_sensitivity=self.contour_edge_sensitivity / 100.0,
                    edge_blur=int(self.contour_edge_blur / 100.0 * 5) if self.contour_edge_blur > 0 else 0,
                    wave_speed=self.contour_wave_speed / 100.0,
                    amplitude=self.contour_amplitude / 100.0,
                    layers=self.contour_layers,
                    glow=self.contour_glow / 100.0,
                )
            except Exception:
                return self._render_particles(t)
        
        elif self.mode == "audioreactive_alt":
            # Apply audio-reactive overlays on ORIGINAL color image, then ASCII-render
            try:
                from asciinator.core.audio_input import AudioInput
                from asciinator.core.audio_analyzer import SixBandAnalyzer
                from PIL import Image
                
                if self.img_color is None:
                    return self.base_gray
                
                # Initialize audio
                if not hasattr(self, '_audio_input'):
                    self._audio_input = AudioInput(samplerate=48000, blocksize=1024, channels=1)
                    self._audio_input.start()
                if not hasattr(self, '_audio_an'):
                    self._audio_an = SixBandAnalyzer(samplerate=48000)
                samples = self._audio_input.get_latest(2048)
                bands = self._audio_an.process(samples)
                self._audio_bands = bands
                
                # Use cached full-resolution edges; compute if missing
                if not hasattr(self, '_cached_edges_full') or self._cached_edges_full is None:
                    try:
                        from asciinator.core.edges import get_edge_data
                        gray_full = to_grayscale(self.img_color)
                        g_norm = gray_full.astype(np.float32) / 255.0
                        edges_full, dist_full = get_edge_data((self.img_h, self.img_w, 0), g_norm.tobytes())
                        self._cached_edges_full = edges_full
                        self._cached_dist_full = dist_full
                    except Exception:
                        self._cached_edges_full = None
                        self._cached_dist_full = None
                
                color_base = self.img_color.astype(np.float32)
                h, w = color_base.shape[0], color_base.shape[1]
                overlay_factor = np.ones((h, w), dtype=np.float32)
                t = time.time()
                
                outline_enabled = getattr(self, 'chk_outline', None) and self.chk_outline.isChecked()
                rays_enabled = getattr(self, 'chk_rays', None) and self.chk_rays.isChecked()
                bands_enabled = getattr(self, 'chk_bands', None) and self.chk_bands.isChecked()
                sparkles_enabled = getattr(self, 'chk_sparkles', None) and self.chk_sparkles.isChecked()
                echo_enabled = getattr(self, 'chk_echo', None) and self.chk_echo.isChecked()
                bg_enabled = getattr(self, 'chk_bg', None) and self.chk_bg.isChecked()
                
                edges_full = getattr(self, '_cached_edges_full', None)
                dist_full = getattr(self, '_cached_dist_full', None)

                use_gpu = getattr(self, 'chk_gpu', None) and self.chk_gpu.isChecked()
                gpu_available = False
                if use_gpu:
                    try:
                        import torch
                        gpu_available = torch.cuda.is_available()
                    except Exception:
                        gpu_available = False
                if outline_enabled and edges_full is not None:
                    level = float(0.6 * bands[1] + 0.4 * bands[2])
                    if level > 0.01:
                        outline_mask = edges_full > 0.5
                        overlay_factor[outline_mask] *= (1.0 + 3.0 * level)
                
                if gpu_available:
                    # Torch-CUDA accelerated overlays
                    import torch
                    device = torch.device('cuda')
                    tbands = torch.tensor(bands, device=device, dtype=torch.float32)
                    tf = torch.from_numpy(color_base).to(device=device, dtype=torch.float32)
                    of = torch.ones((h, w), device=device, dtype=torch.float32)
                    if edges_full is not None:
                        tedges = torch.from_numpy((edges_full > 0.5).astype(np.uint8)).to(device=device, dtype=torch.uint8)
                    else:
                        tedges = None
                    if dist_full is not None:
                        tdist = torch.from_numpy(dist_full).to(device=device, dtype=torch.float32)
                    else:
                        tdist = None
                    # Outline
                    if outline_enabled and tedges is not None:
                        lvl = 0.6 * tbands[1] + 0.4 * tbands[2]
                        if float(lvl) > 0.01:
                            of = torch.where(tedges > 0, of * (1.0 + 3.0 * lvl), of)
                    # Rays (distance falloff)
                    if rays_enabled:
                        lvl = 0.4 * tbands[0] + 0.4 * tbands[1] + 0.2 * tbands[4]
                        if float(lvl) > 0.01 and tdist is not None:
                            max_len = float(self.rays_length.value())
                            intensity = float(self.rays_intensity.value())
                            gain = intensity * float(lvl)
                            # Smooth falloff: exp(-d / s)
                            s = max(1.0, max_len * 0.3)
                            of = of * (1.0 + gain * torch.exp(-tdist / s))
                    # Bands breathing
                    if bands_enabled:
                        lvl = 0.3 * tbands[0] + 0.7 * tbands[1]
                        if float(lvl) > 0.01:
                            breath = math.sin(t * 5.0) * float(lvl) * 2.0
                            of = of * (1.0 + breath)
                    # Sparkles along edges
                    if sparkles_enabled:
                        lvl = 0.5 * tbands[4] + 0.5 * tbands[5]
                        if float(lvl) > 0.01:
                            density = float(self.sparkles_density.value())
                            gain = float(self.sparkles_gain.value())
                            rand = torch.rand((h, w), device=device)
                            base = (tedges > 0) if tedges is not None else (rand > 0.0)
                            smask = (rand < (density * (0.2 + 0.8 * float(lvl)))) & base
                            of = torch.where(smask, of * (1.0 + gain * float(lvl)), of)
                    # Echo isolines
                    if echo_enabled and tdist is not None:
                        spacing = float(self.echo_spacing.value())
                        bandw = float(self.echo_band.value())
                        count = int(max(0, self.echo_lines.value()))
                        if spacing > 0 and count > 0:
                            level = 0.3 * tbands[2] + 0.7 * tbands[3]
                            if float(level) > 0.005:
                                for k in range(1, count + 1):
                                    target = k * spacing
                                    band_mask = (torch.abs(tdist - target) <= bandw * 0.5)
                                    of = torch.where(band_mask, of * (1.0 + 0.5 * float(level)), of)
                    # Background
                    if bg_enabled:
                        bg_int = float(self.bg_intensity.value())
                        bg_speed = float(self.bg_speed.value())
                        if bg_int > 0.0:
                            yy, xx = torch.meshgrid(torch.arange(h, device=device), torch.arange(w, device=device), indexing='ij')
                            wave = torch.sin(0.02 * xx + 0.02 * yy + t * bg_speed)
                            lvl = 0.6 * tbands[0] + 0.4 * tbands[1]
                            of = of * (1.0 + bg_int * float(lvl) * (0.5 + 0.5 * wave))
                    # Compose
                    final_rgb = torch.clamp(tf * of.unsqueeze(-1), 0.0, 255.0).to(dtype=torch.uint8).cpu().numpy()
                else:
                    # CPU vectorized path
                    if rays_enabled:
                        level = float(0.4 * bands[0] + 0.4 * bands[1] + 0.2 * bands[4])
                        if level > 0.01 and dist_full is not None:
                            max_len = float(self.rays_length.value())
                            intensity = float(self.rays_intensity.value())
                            s = max(1.0, max_len * 0.3)
                            gain = intensity * level * np.exp(-dist_full / s)
                            overlay_factor *= (1.0 + gain)
                    level = float(0.4 * bands[0] + 0.4 * bands[1] + 0.2 * bands[4])
                    if level > 0.01:
                        # distance-based falloff along normals: approximate by dilating edge mask
                        edge_mask = (edges_full > 0.5) if edges_full is not None else None
                        if edge_mask is not None:
                            max_len = int(max(1, self.rays_length.value()))
                            intensity = float(self.rays_intensity.value())
                            for d in range(max_len):
                                gain = intensity * level * (1.0 - d / max_len)
                                if gain <= 0:
                                    break
                                # simple expansion: shift masks in 4 dirs (approx normal expansion)
                                shifted = np.zeros_like(edge_mask, dtype=bool)
                                shifted[1:, :] |= edge_mask[:-1, :]
                                shifted[:-1, :] |= edge_mask[1:, :]
                                shifted[:, 1:] |= edge_mask[:, :-1]
                                shifted[:, :-1] |= edge_mask[:, 1:]
                                edge_mask = shifted
                                overlay_factor[edge_mask] *= (1.0 + gain)
                        else:
                            ray_mask = np.random.random((h, w)) < level * 0.2
                            overlay_factor[ray_mask] *= (1.0 + level * 4.0)
                
                if bands_enabled:
                    level = float(0.3 * bands[0] + 0.7 * bands[1])
                    if level > 0.01:
                        breath = np.sin(t * 5.0) * level * 2.0
                        overlay_factor *= (1.0 + breath)
                
                if sparkles_enabled:
                    level = float(0.5 * bands[4] + 0.5 * bands[5])
                    if level > 0.01:
                        density = float(self.sparkles_density.value())
                        gain = float(self.sparkles_gain.value())
                        base_mask = (edges_full > 0.5) if edges_full is not None else (np.ones((h, w), dtype=bool))
                        rand = np.random.random((h, w))
                        sparkle_mask = (rand < (density * (0.2 + 0.8 * level))) & base_mask
                        overlay_factor[sparkle_mask] *= (1.0 + gain * level)

                # Echo silhouette lines via distance field isolines
                if echo_enabled and getattr(self, '_cached_dist_full', None) is not None:
                    df = self._cached_dist_full
                    spacing = float(self.echo_spacing.value())
                    bandw = float(self.echo_band.value())
                    count = int(max(0, self.echo_lines.value()))
                    if spacing > 0 and count > 0:
                        for k in range(1, count + 1):
                            target = k * spacing
                            band_mask = (np.abs(df - target) <= bandw * 0.5)
                            # modulate by mids
                            level = float(0.3 * bands[2] + 0.7 * bands[3])
                            if level > 0.005:
                                overlay_factor[band_mask] *= (1.0 + 0.5 * level)

                # Background audio-reactive layer
                if bg_enabled:
                    bg_int = float(self.bg_intensity.value())
                    bg_speed = float(self.bg_speed.value())
                    if bg_int > 0.0:
                        yy, xx = np.mgrid[0:h, 0:w]
                        wave = np.sin(0.02 * xx + 0.02 * yy + t * bg_speed)
                        lvl = float(0.6 * bands[0] + 0.4 * bands[1])
                        overlay_factor *= (1.0 + bg_int * lvl * (0.5 + 0.5 * wave))
                
                # Apply overlay to original color image
                if gpu_available:
                    pass  # already computed final_rgb
                else:
                    final_rgb = np.clip(color_base * overlay_factor[..., None], 0, 255).astype(np.uint8)
                
                # Convert to grayscale and to ASCII grid
                try:
                    gray_final = to_grayscale(final_rgb)
                    grid, _, _ = resize_to_char_grid(gray_final, self.cell_w, self.cell_h, self.grid_cols, self.grid_rows)
                    # push to GL preview if enabled
                    if hasattr(self, 'gl_preview') and self.gl_preview is not None and self.gl_preview.isVisible():
                        try:
                            # feed grid, edges and distance
                            self.gl_preview.update_grid(grid)
                            # Build and upload ASCII atlas if not set
                            if getattr(self.gl_preview, '_tex_atlas', None) is not None and int(self.gl_preview._params.get('useAtlas', 0)) == 0:
                                from asciinator.utils.atlas import build_glyph_atlas
                                ramp = self.custom_ramp if (self.custom_ramp and len(self.custom_ramp) >= 2) else (ASCII_RAMP_EXT if self.use_extended else ASCII_RAMP_PURE)
                                atlas_img, tiles_x, tiles_y = build_glyph_atlas(self.font_pil, ''.join(ramp), int(self.cell_w), int(self.cell_h))
                                self.gl_preview.upload_atlas(atlas_img, tiles_x, tiles_y)
                            if getattr(self, '_cached_edges_full', None) is not None and getattr(self, '_cached_dist_full', None) is not None:
                                # Resize cached maps to grid size
                                from PIL import Image as _PIL
                                e_full = (self._cached_edges_full * 255.0).astype(np.uint8)
                                d_full = self._cached_dist_full.astype(np.float32)
                                e_img = _PIL.fromarray(e_full, 'L').resize((grid.shape[1], grid.shape[0]), _PIL.NEAREST)
                                d_max = max(1.0, float(max(d_full.shape)))
                                d_norm = (d_full / d_max * 255.0).clip(0,255).astype(np.uint8)
                                d_img = _PIL.fromarray(d_norm, 'L').resize((grid.shape[1], grid.shape[0]), _PIL.BILINEAR)
                                self.gl_preview.update_edges_dist(np.array(e_img, dtype=np.uint8)/255.0, np.array(d_img, dtype=np.uint8))
                            # toggles, bands, params, time
                            outline_enabled = getattr(self, 'chk_outline', None) and self.chk_outline.isChecked()
                            rays_enabled = getattr(self, 'chk_rays', None) and self.chk_rays.isChecked()
                            echo_enabled = getattr(self, 'chk_echo', None) and self.chk_echo.isChecked()
                            sparkles_enabled = getattr(self, 'chk_sparkles', None) and self.chk_sparkles.isChecked()
                            bg_enabled = getattr(self, 'chk_bg', None) and self.chk_bg.isChecked()
                            self.gl_preview.set_toggles(outline_enabled, rays_enabled, echo_enabled, sparkles_enabled, bg_enabled)
                            self.gl_preview.set_bands(self._audio_bands if hasattr(self, '_audio_bands') else np.zeros(6, dtype=np.float32))
                            self.gl_preview.set_params(
                                raysLength=float(self.rays_length.value()),
                                raysIntensity=float(self.rays_intensity.value()),
                                echoSpacing=float(self.echo_spacing.value()),
                                echoBand=float(self.echo_band.value()),
                                echoLines=int(self.echo_lines.value()),
                                sparklesDensity=float(self.sparkles_density.value()),
                                sparklesGain=float(self.sparkles_gain.value()),
                                bgIntensity=float(self.bg_intensity.value()),
                                bgSpeed=float(self.bg_speed.value()),
                                useAtlas=1,
                            )
                            # Palette from color_stops (convert to 0..1 RGB)
                            try:
                                cols = []
                                for stop in self.color_stops:
                                    r, g, b = stop[1]
                                    cols.append([r/255.0, g/255.0, b/255.0])
                                if cols:
                                    self.gl_preview.set_palette(np.array(cols, dtype=np.float32))
                            except Exception:
                                pass
                            self.gl_preview.set_time(time.time())
                        except Exception:
                            pass
                    return grid
                except Exception:
                    return self.base_gray
            except Exception:
                return self.base_gray
            
        return self.base_gray
    
    def _render_contourswim(self, t):
        # Рендер режима 'contourswim' - эффект плавающих контуров
        if self.base_gray is None:
            return None
            
        # Работаем напрямую с базовым изображением БЕЗ волн
        base_image = self.base_gray.copy()
        rows, cols = base_image.shape
        
        # Находим края с учетом чувствительности
        sensitivity = self.contour_edge_sensitivity / 100.0  # 0.0 - 1.0
        edges = self._detect_simple_edges(base_image, sensitivity)
        
        # Применяем размытие к краям если нужно: scipy (если доступна) или fallback
        if self.contour_edge_blur > 0:
            blur_amount = max(1, int(self.contour_edge_blur / 100.0 * 5))  # 1-5
            if SCIPY_AVAILABLE:
                edges = _scipy_gaussian_filter(edges, sigma=blur_amount)
            else:
                edges = self._gaussian_blur_numpy(edges, blur_amount)
        
        # Создаем анимированные волны на краях
        wave_speed = self.contour_wave_speed / 100.0  # 0.0 - 2.0
        amplitude = self.contour_amplitude / 100.0  # 0.0 - 1.0
        layers = self.contour_layers  # 1-5
        effect = self._animate_fire_on_edges(edges, t, rows, cols, wave_speed, amplitude, layers)
        
        # Яркость свечения (0.0 - 1.0)
        glow = self.contour_glow / 100.0
        
        # Результат: базовое изображение + яркий эффект на краях
        result = base_image.copy()
        
        # Применяем эффект там, где есть края
        threshold = 0.1 * (1.0 - sensitivity * 0.5)  # Чем выше чувствительность, тем ниже порог
        effect_mask = edges > threshold
        result[effect_mask] = np.clip(
            result[effect_mask] + effect[effect_mask] * glow,
            0.0, 1.0
        )
        
        return result

    def _gaussian_blur_numpy(self, img, radius):
        # Простое приближение гаусса через два прохода box blur
        if radius <= 0:
            return img
        h, w = img.shape
        # По X
        temp = np.zeros_like(img)
        for y in range(h):
            for x in range(w):
                x0 = max(0, x - radius); x1 = min(w - 1, x + radius)
                temp[y, x] = img[y, x0:x1+1].mean()
        # По Y
        out = np.zeros_like(img)
        for x in range(w):
            for y in range(h):
                y0 = max(0, y - radius); y1 = min(h - 1, y + radius)
                out[y, x] = temp[y0:y1+1, x].mean()
        return out
    
    def _detect_simple_edges(self, image, sensitivity=0.3):
        # Простое обнаружение краев с учетом чувствительности
        rows, cols = image.shape
        edges = np.zeros_like(image)
        
        # Простой edge detection - разница с соседями
        for i in range(1, rows-1):
            for j in range(1, cols-1):
                # Вычисляем разницу с соседями
                diff = abs(image[i, j] - image[i-1, j]) + \
                       abs(image[i, j] - image[i+1, j]) + \
                       abs(image[i, j] - image[i, j-1]) + \
                       abs(image[i, j] - image[i, j+1])
                edges[i, j] = diff / 4.0
        
        # Нормализуем
        if edges.max() > 0:
            edges = edges / edges.max()
        
        # Применяем чувствительность (усиливаем или ослабляем края)
        # sensitivity 0.0 = слабые края, 1.0 = сильные края
        edges = np.power(edges, 1.0 - sensitivity * 0.5)
        
        return edges
    
    def _animate_fire_on_edges(self, edges, t, rows, cols, wave_speed=1.0, amplitude=0.5, layers=3):
        # Создание анимированных волн на краях
        fire = np.zeros((rows, cols))
        
        # Создаем координатные сетки
        y_coords = np.arange(rows)[:, np.newaxis]
        x_coords = np.arange(cols)[np.newaxis, :]
        
        # Создаем несколько слоев волн (от 1 до 5)
        animation = np.zeros((rows, cols))
        
        for i in range(layers):
            # Параметры для каждого слоя
            freq_mult = 2.0 + i * 1.0  # Частота увеличивается с каждым слоем
            phase_x = 0.1 + i * 0.05
            phase_y = 0.15 - i * 0.05
            weight = 1.0 / (i + 1)  # Первый слой самый сильный
            
            # Создаем волну с учетом скорости
            wave = np.sin(t * freq_mult * wave_speed + x_coords * phase_x + y_coords * phase_y)
            animation += wave * weight
        
        # Нормализуем и применяем амплитуду
        animation = (animation / layers) * amplitude * 0.5 + 0.5
        animation = np.clip(animation, 0.0, 1.0)
        
        # Применяем к краям
        fire = edges * animation
        
        # Усиливаем яркость (контраст)
        fire = np.power(fire, 0.6)
        
        return fire
    
    def _apply_filter(self, image, kernel):
        # Применение фильтра к изображению
        rows, cols = image.shape
        result = np.zeros_like(image)
        
        k_h, k_w = kernel.shape
        pad_h, pad_w = k_h // 2, k_w // 2
        
        # Простая свертка
        for i in range(pad_h, rows - pad_h):
            for j in range(pad_w, cols - pad_w):
                result[i, j] = np.sum(image[i-pad_h:i+pad_h+1, j-pad_w:j+pad_w+1] * kernel)
        
        return result
    
        
    def render_frame_pil(self, t=None, font=None, cell_w=None, cell_h=None, use_cache=True, for_preview=False):
        # Рендер кадра с оптимизациями
        # use_cache: использовать кэш глифов (для preview)
        # for_preview: уменьшать сетку для preview
        if self.base_gray is None:
            return None
        if t is None:
            t = self.t
            
        g = self.render_frame_gray(t)
        if g is None:
            return None
        
        # If upstream returned RGB, convert to grayscale for ASCII stage
        if len(g.shape) == 3 and g.shape[2] == 3:
            g = np.mean(g, axis=2).astype(np.uint8)
            
        # Downsampling для preview
        if for_preview:
            rows, cols = g.shape
            max_dim = max(rows, cols)
            
            if max_dim > self.max_preview_cells:
                # Уменьшаем сетку
                scale = self.max_preview_cells / max_dim
                new_rows = max(8, int(rows * scale))
                new_cols = max(8, int(cols * scale))
                
                # Resize grid
                pil_temp = Image.fromarray((g*255).astype(np.uint8)).convert('L')
                pil_resized = pil_temp.resize((new_cols, new_rows), Image.BICUBIC)
                g = np.array(pil_resized, dtype=np.float32) / 255.0
        
        # Выбираем набор символов: приоритет кастомным символам
        if self.custom_ramp and len(self.custom_ramp) >= 2:
            ramp = self.custom_ramp
        elif self.use_extended:
            ramp = ASCII_RAMP_EXT
        else:
            ramp = ASCII_RAMP_PURE
            
        f = font if font is not None else self.font_pil
        cw = cell_w if cell_w is not None else self.cell_w
        ch = cell_h if cell_h is not None else self.cell_h
        
        cache = self.glyph_cache if use_cache else None
        
        return build_ascii_image_color(
            g, ramp, f, cw, ch, self.color_stops,
            invert=False, gap_x=self.gap_x, gap_y=self.gap_y,
            bg_color=self.render_bg, glyph_cache=cache
        )
        
    def update_preview(self, force=False):
        if self.base_gray is None:
            return
            
        import time
        start_time = time.time()
        
        # Рендер с оптимизациями для preview
        img = self.render_frame_pil(use_cache=True, for_preview=True)
        if img is None:
            return
            
        qimg = self.qimage_from_pil(img)
        
        # Применяем PostFX к preview
        qimg = self.postfx.apply_preview_fx(qimg)
        
        self.preview.set_image(qimg)
        
        # Обновляем второе окно (если есть)
        if self.second is not None and self.second.isVisible():
            # Для второго окна тоже используем оптимизацию
            self.second.set_image(qimg)
            
        # Измеряем время рендера
        render_time = time.time() - start_time
        self.last_render_time = render_time
        
        # Если рендер медленный - включаем пропуск кадров
        if render_time > 0.05:  # Больше 50ms
            self.skip_frames = True
        elif render_time < 0.03:  # Меньше 30ms
            self.skip_frames = False
            
    @staticmethod
    def qimage_from_pil(pil_img):
        rgb = pil_img.convert('RGBA')
        data = rgb.tobytes('raw', 'RGBA')
        qimg = QImage(data, rgb.width, rgb.height, QImage.Format_RGBA8888)
        return qimg

def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app = QApplication(sys.argv)
        w = MainWindow()
        w.show()
        sys.exit(app.exec())
    except Exception as e:
        # Показываем ошибку в MessageBox если что-то пошло не так
        import traceback
        error_msg = f"Критическая ошибка:\n\n{str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)
        try:
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Ошибка запуска")
            msg.setText(error_msg)
            msg.exec()
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
