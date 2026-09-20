from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QFont


class Bubble(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignCenter)

        self.setStyleSheet("""
            QLabel {
                color: #001a14;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: bold;
                padding: 10px 14px;
            }
        """)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def say(self, text, ms=3500):
        self.setText(text)
        self.adjustSize()
        self.resize(self.width() + 20, self.height() + 20)
        self.show()
        self.raise_()
        self.hide_timer.start(ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -12)  # dejamos espacio abajo para la colita

        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)

        # Colita (triangulito abajo)
        cx = self.width() // 2
        path.moveTo(cx - 8, rect.bottom())
        path.lineTo(cx, rect.bottom() + 10)
        path.lineTo(cx + 8, rect.bottom())
        path.closeSubpath()

        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(QPen(QColor(0, 80, 60), 2))
        painter.drawPath(path)

        super().paintEvent(event)