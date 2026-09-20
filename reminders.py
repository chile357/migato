# MODIFICADO POR: Yair - Sistemas Quiver
# Razón: frases variadas para agua, pausa visual y gym

import random
from datetime import datetime
from PySide6.QtCore import QTimer


class Reminders:
    """Recordatorios programados: agua, pausa visual, gym."""

    AGUA_MSGS = [
        "Bebe agua 💧",
        "¿Cuándo tomaste agua por última vez?",
        "Hidratación, humano.",
        "Agua. Ahora.",
        "Tu cuerpo necesita agua~",
        "💧 Agua, por favor.",
    ]

    PAUSA_MSGS = [
        "Mira lejos 20 segundos 👀",
        "Descansa los ojos un momento.",
        "20-20-20: 20 seg mirando a 20 pies.",
        "Parpadea. En serio.",
        "Tus ojos me lo agradecerán.",
        "Pausa visual. Ya.",
    ]

    GYM_MSGS = [
        "¿Irás al gym hoy? 🏋️",
        "Hoy toca ejercicio~",
        "El gym no va a ir a ti solo.",
        "¿Día de gym? Ánimo.",
        "Recuerda: gym hoy 💪",
    ]

    def __init__(self, on_reminder):
        self.on_reminder       = on_reminder
        self.last_water        = datetime.now()
        self.last_pause        = datetime.now()
        self.gym_alerted_today = None

        t = QTimer()
        t.timeout.connect(self.check)
        t.start(60 * 1000)
        self._timer = t

    def check(self):
        now = datetime.now()

        # Gym: lun(0) mar(1) jue(3) vie(4) entre 7:00 y 7:30
        if now.weekday() in (0, 1, 3, 4):
            if now.hour == 7 and 0 <= now.minute <= 30:
                if self.gym_alerted_today != now.date():
                    self.gym_alerted_today = now.date()
                    self.on_reminder("gym", random.choice(self.GYM_MSGS))

        # Agua cada 60 min
        if (now - self.last_water).total_seconds() >= 60 * 60:
            self.last_water = now
            self.on_reminder("agua", random.choice(self.AGUA_MSGS))

        # Pausa visual cada 20 min
        if (now - self.last_pause).total_seconds() >= 20 * 60:
            self.last_pause = now
            self.on_reminder("pausa", random.choice(self.PAUSA_MSGS))