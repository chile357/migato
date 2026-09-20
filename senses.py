# MODIFICADO POR: Yair - Sistemas Quiver
# Razón: detección de inactividad del ratón (5 min), más keywords de ventanas,
#        frases más variadas por contexto, callback on_inactive separado

import time
import ctypes
import random
from datetime import datetime

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor


class Senses:
    def __init__(self, on_event, on_inactive=None):
        self.on_event    = on_event
        self.on_inactive = on_inactive

        self.start_time      = time.time()
        self.last_clipboard  = ""
        self.last_window     = ""
        self.last_mouse_pos  = QCursor.pos()
        self.last_mouse_time = time.time()
        self._inactive_fired = False   # evitar spam de inactividad

        # Portapapeles cada 2 s
        self._timer(2000, self.check_clipboard)

        # Descanso cada 5 min
        self._timer(5 * 60 * 1000, self.check_rest)

        # Ventana activa cada 5 s
        self._timer(5000, self.check_window)

        # Inactividad del ratón cada 30 s
        self._timer(30 * 1000, self.check_mouse_inactive)

    def _timer(self, ms, fn):
        t = QTimer()
        t.timeout.connect(fn)
        t.start(ms)
        return t

    # ------------------------------------------------------------------ hora
    def greeting(self):
        h = datetime.now().hour
        greetings = {
            range(6,  12): ["¡Buenos días!", "¡Arriba!", "¿Ya desayunaste?"],
            range(12, 19): ["¡Buenas tardes!", "¿Cómo va el día?", "Tarde productiva~"],
            range(19, 24): ["¡Buenas noches!", "Ya es noche...", "¿Aún trabajando?"],
        }
        for r, msgs in greetings.items():
            if h in r:
                return random.choice(msgs)
        return random.choice(["¿Aún despierto? Son horas...", "Es muy tarde...", "Duérmete ya."])

    def is_late(self):
        h = datetime.now().hour
        return h >= 23 or h < 6

    # ------------------------------------------------------------------ portapapeles
    def check_clipboard(self):
        text = QApplication.clipboard().text().strip()
        if not text or text == self.last_clipboard:
            return
        self.last_clipboard = text
        short = text[:35] + ("..." if len(text) > 35 else "")
        msgs = [
            f'Copiaste: "{short}"',
            f'Hmm... "{short}"',
            f'¿Eso qué es? "{short}"',
        ]
        self.on_event("clipboard", random.choice(msgs))

    # ------------------------------------------------------------------ descanso
    def check_rest(self):
        mins = int((time.time() - self.start_time) / 60)
        if mins > 0 and mins % 30 == 0:
            msgs = [
                f"Llevas {mins} min trabajando. ¿Descansas?",
                f"{mins} minutos ya. Párate un momento.",
                f"¡{mins} min! Estira las piernas.",
            ]
            self.on_event("descanso", random.choice(msgs))

    def time_worked(self):
        return int((time.time() - self.start_time) / 60)

    # ------------------------------------------------------------------ ventana
    def active_window_title(self):
        try:
            user32 = ctypes.windll.user32
            hwnd   = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf    = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or ""
        except Exception:
            return ""

    def check_window(self):
        title = self.active_window_title()
        if not title or title == self.last_window:
            return
        self.last_window = title
        low = title.lower()

        rules = [
            (["visual studio code", "pycharm", "sublime", "cursor", "vim", "neovim", "nvim"],
             ["¿Programando? Miau.", "Código de nuevo...", "¡A programar!", "¿Bugs o features?"]),
            (["youtube", "netflix", "twitch", "prime video", "disney"],
             ["¿Viendo algo? Yo también quiero.", "¡Pónme algo bueno!", "Oye, comparte la pantalla."]),
            (["spotify", "music", "deezer", "apple music"],
             ["¿Música? Mmm~", "¡Buena canción!", "Me gusta el ritmo."]),
            (["chrome", "firefox", "edge", "brave", "opera"],
             ["Navegando...", "¿Qué buscas?", "Internet otra vez..."]),
            (["discord", "whatsapp", "telegram", "slack", "teams"],
             ["¿Chateando? Salúdame.", "¡Diles hola de mi parte!", "¿De qué hablan?"]),
            (["steam", "game", "juego", "epic games", "battle.net"],
             ["¡Estás jugando! ¿Me dejas ver?", "¡Gana!", "¿Puedo jugar yo también?"]),
            (["word", "excel", "powerpoint", "docs", "sheets", "notion"],
             ["Trabajando en documentos...", "Mucho texto...", "¿Cuándo terminas?"]),
            (["claude", "chatgpt", "gemini", "copilot", "deepseek"],
             ["¿Hablando con otra IA? 😾", "Oye... yo existo.", "¿Te trato mal o qué?"]),
            (["figma", "photoshop", "illustrator", "canva", "gimp"],
             ["¡Diseñando! Qué chido.", "¿Me dibujas a mí?", "Hazme un retrato~"]),
            (["zoom", "meet", "teams", "webex", "call"],
             ["¿Videollamada? No hagas ruido.", "Silencio, estás en junta.", "¡Peinarte primero!"]),
        ]

        for keywords, msgs in rules:
            if any(k in low for k in keywords):
                self.on_event("ventana", random.choice(msgs))
                return

    # ------------------------------------------------------------------ inactividad ratón
    def check_mouse_inactive(self):
        pos  = QCursor.pos()
        now  = time.time()

        if pos != self.last_mouse_pos:
            # Ratón se movió — resetear
            self.last_mouse_pos  = pos
            self.last_mouse_time = now
            self._inactive_fired = False
            return

        elapsed = now - self.last_mouse_time
        if elapsed >= 5 * 60 and not self._inactive_fired:
            self._inactive_fired = True
            if self.on_inactive:
                self.on_inactive()