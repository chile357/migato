# MODIFICADO POR: Yair - Sistemas Quiver
# Razón: refactor completo — mood system, follow cursor, pounce real,
#        inactividad 5min, bordes suaves, calm_down con estado, trim con numpy
#        + soporte para ejecutable (PyInstaller)
#        + persistencia de estado y system tray
#        + CEREBRO v2: utility AI, hambre/aburrimiento/afecto/estrés,
#          detección de actividad del usuario, memoria persistente,
#          frases contextuales, huida del cursor, saludo al volver.

import random
import time
import sys
import os
import json

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from PySide6.QtWidgets import (
    QWidget, QLabel, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint
from PySide6.QtGui import (
    QPixmap, QTransform, QImage, QCursor, QPainter, QIcon, QAction
)

from bubble import Bubble
from senses import Senses
from reminders import Reminders


COLS = 6
ROWS = 4
BOX  = 100

ANIMATIONS = {
    "idle":    [(0, 0), (1, 0)],
    "walk":    [(3, 0), (4, 0), (5, 0)],
    "run":     [(1, 1), (2, 1), (3, 1), (4, 1)],
    "sleep":   [(0, 2), (1, 2)],
    "front":   [(2, 2), (3, 2), (4, 2)],
    "stretch": [(5, 2), (0, 3)],
    "clean":   [(1, 3), (2, 3)],
    "pounce":  [(3, 3), (4, 3)],
    "meow":    [(5, 3)],
}

# ---------------------------------------------------------------------------
# Frases por mood
# ---------------------------------------------------------------------------
PHRASES = {
    "happy": [
        "¡Miau~!", "¡Hola humano!", "¡Juega conmigo!",
        "¡Qué buen día!", "Estoy feliz 😸", "¿Me haces cariño?",
        "¡Me encanta estar aquí!", "Miau miau miau~",
    ],
    "normal": [
        "Miau.", "¿Trabajando otra vez?", "Tengo hambre...",
        "¿Ya terminaste?", "Qué aburrido.", "No olvides descansar.",
        "¿Un cafecito?", "Estoy aburrido...", "Hmm...",
        "¿En qué piensas?", "Oye.", "...",
    ],
    "tired": [
        "Tengo sueño...", "Cansado...", "Zzz casi...",
        "No puedo más...", "¿Descansamos?", "Mis patitas...",
    ],
    "late": [
        "Deberías dormir...", "Es muy tarde.", "Yo ya tengo sueño.",
        "¿No te cansas?", "Mañana sigue igual...",
    ],
    "morning": [
        "¡Buenos días!", "¿Ya desayunaste?", "Empecemos bien el día.",
        "¡Arriba!", "Mmm... café...",
    ],
    "hungry": [
        "¡Comida!", "Miau... hambre...", "¿Ya comiste tú?",
        "Yo no he comido 👀", "Estómago gruñendo...",
        "Necesito croquetas 🍣", "Miau miau (traducción: comida)",
    ],
    "lonely": [
        "Te extrañé...", "¿Dónde estabas?", "No me ignores 😿",
        "Ven a jugar...", "Estoy solito...", "¿Sigues ahí?",
        "Ya vuelve, humano.",
    ],
    "playful": [
        "¡Atrápame!", "¡Juguemos!", "¡Corre, corre!",
        "¡Miau! ¡Vamos!", "¡Te voy a atrapar!",
    ],
    "stressed": [
        "¡Miau! ¡Aléjate!", "¡Me asustas!", "¡No!",
        "¡Eso no me gusta!", "¡Ay!",
    ],
}


def _base_path():
    """Devuelve la carpeta base, funcione como script o como EXE."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _save_path():
    """Carpeta de guardado (junto al EXE o al script)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "save.json")


# ---------------------------------------------------------------------------
# Trim rápido con numpy, fallback puro
# ---------------------------------------------------------------------------
def trim(pixmap: QPixmap):
    """Recorta transparencia. Retorna (pixmap_recortado, QRect bbox)."""
    img = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()

    if _NUMPY:
        ptr = img.bits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
        alpha = arr[:, :, 3]
        mask = alpha > 10
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any():
            return pixmap, QRect(0, 0, w, h)
        top    = int(np.argmax(rows))
        bottom = int(len(rows) - np.argmax(rows[::-1]) - 1)
        left   = int(np.argmax(cols))
        right  = int(len(cols) - np.argmax(cols[::-1]) - 1)
    else:
        left, right, top, bottom = w, 0, h, 0
        for y in range(h):
            for x in range(w):
                if (img.pixel(x, y) >> 24) & 0xFF > 10:
                    if x < left:   left   = x
                    if x > right:  right  = x
                    if y < top:    top    = y
                    if y > bottom: bottom = y
        if right <= left or bottom <= top:
            return pixmap, QRect(0, 0, w, h)

    rect = QRect(left, top, right - left + 1, bottom - top + 1)
    return pixmap.copy(rect), rect


# ---------------------------------------------------------------------------
# Pet
# ---------------------------------------------------------------------------
class Pet(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ---- Cargar sprite sheet (soporta script y EXE) ----
        sheet_path = os.path.join(_base_path(), "assets", "cat_sheet.png")
        sheet  = QPixmap(sheet_path)
        cell_w = sheet.width()  // COLS
        cell_h = sheet.height() // ROWS

        raw_frames  = {}
        frame_sizes = {}
        for name, coords in ANIMATIONS.items():
            raw_frames[name]  = []
            frame_sizes[name] = []
            for col, row in coords:
                cell = sheet.copy(QRect(col * cell_w, row * cell_h, cell_w, cell_h))
                trimmed, rect = trim(cell)
                raw_frames[name].append(trimmed)
                frame_sizes[name].append((rect.width(), rect.height()))

        ref_h        = max(h for (_, h) in frame_sizes["idle"])
        scale_factor = BOX / ref_h

        self.frames = {}
        for name, pixmaps in raw_frames.items():
            self.frames[name] = []
            for i, trimmed in enumerate(pixmaps):
                tw, th     = frame_sizes[name][i]
                target_sw  = max(1, int(tw * scale_factor))
                target_sh  = max(1, int(th * scale_factor))
                scaled     = trimmed.scaled(target_sw, target_sh,
                                            Qt.IgnoreAspectRatio,
                                            Qt.SmoothTransformation)
                canvas = QPixmap(BOX, BOX)
                canvas.fill(Qt.transparent)
                p = QPainter(canvas)
                p.drawPixmap((BOX - scaled.width()) // 2,
                             (BOX - scaled.height()) // 2, scaled)
                p.end()
                self.frames[name].append((canvas,
                                          canvas.transformed(QTransform().scale(-1, 1))))

        # ---- Label sprite ----
        self.sprite = QLabel(self)
        self.sprite.setAlignment(Qt.AlignCenter)
        self.sprite.setFixedSize(BOX, BOX)
        self.resize(BOX, BOX)

        # ---- Bubble ----
        self.bubble = Bubble()

        # ---- Senses & Reminders ----
        self.senses    = Senses(on_event=self.react_to_sense,
                                on_inactive=self.react_to_inactivity)
        self.reminders = Reminders(on_reminder=self.react_to_reminder)

        # ---- Estado visual / físico ----
        self.state          = "idle"
        self.frame_index    = 0
        self.sleep_frame    = 0
        self.direction      = 1
        self.dy             = random.choice([-1, 1])
        self.speed          = 2
        self.drag_pos       = None

        self.ticks_in_state  = 0
        self.state_duration  = random.randint(3, 8)

        # ---- CEREBRO: estado interno ----
        self.energy     = 100.0   # 0-100
        self.hunger     = 30.0    # 0-100 (sube con el tiempo)
        self.boredom    = 20.0    # 0-100 (sube si no interactúas)
        self.affection  = 50.0    # 0-100 (sube con clicks/caricias)
        self.stress     = 0.0     # 0-100 (sube si lo asustas o lo ignoras mucho)

        self.last_interaction = time.time()
        self.last_fed         = time.time()
        self.session_clicks   = 0
        self.session_start    = time.time()
        self.total_clicks     = 0

        # ---- Detección de actividad del usuario ----
        self._last_mouse       = QCursor.pos()
        self.user_idle_seconds = 0

        # Follow cursor
        self.follow_active   = False
        self.follow_timer    = QTimer(self)
        self.follow_timer.timeout.connect(self._stop_follow)

        # Pounce hacia cursor
        self.pounce_target   = None
        self.pounce_steps    = 0

        # Borde suave: margen en px donde empieza a frenar
        self.BORDER_MARGIN   = 80

        # ---- Timers ----
        self._make_timer(50,   self.tick_move)
        self._make_timer(250,  self.tick_anim)
        self._make_timer(3000, self.think)
        self._make_timer(4000, self.look_at_mouse)
        self._make_timer(5000, self.tick_brain)             # metabolismo emocional
        self._make_timer(5000, self.tick_user_activity)     # detecta idle del user
        self._make_timer(30 * 1000, self.save_state)        # autoguardado

        self.think()

        # Cargar estado previo
        self.load_state()

        # System tray
        self.setup_tray()

        QTimer.singleShot(1000, lambda: self.react_to_sense("hora", self.senses.greeting()))

    # ------------------------------------------------------------------ util
    def _make_timer(self, ms, fn):
        t = QTimer(self)
        t.timeout.connect(fn)
        t.start(ms)
        return t

    # ------------------------------------------------------------------ tray
    def setup_tray(self):
        icon_pix = self.frames["idle"][0][0]
        self.tray = QSystemTrayIcon(QIcon(icon_pix), self)
        self.tray.setToolTip("MiGato")

        menu = QMenu()

        act_show = QAction("Mostrar", self)
        act_show.triggered.connect(self.show)
        menu.addAction(act_show)

        act_hide = QAction("Ocultar", self)
        act_hide.triggered.connect(self.hide)
        menu.addAction(act_hide)

        menu.addSeparator()

        act_feed = QAction("Alimentar 🍣", self)
        act_feed.triggered.connect(self.feed)
        menu.addAction(act_feed)

        act_pet = QAction("Acariciar 💕", self)
        act_pet.triggered.connect(self.pet_me)
        menu.addAction(act_pet)

        menu.addSeparator()

        act_reset = QAction("Reiniciar posición", self)
        act_reset.triggered.connect(lambda: self.move(200, 200))
        menu.addAction(act_reset)

        menu.addSeparator()

        act_quit = QAction("Salir", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def quit_app(self):
        self.save_state()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    # ------------------------------------------------------------------ persistencia
    def load_state(self):
        path = _save_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.move(data.get("x", 100), data.get("y", 100))
            self.energy    = data.get("energy", 100.0)
            self.direction = data.get("direction", 1)
            self.hunger    = data.get("hunger", 30.0)
            self.boredom   = data.get("boredom", 20.0)
            self.affection = data.get("affection", 50.0)
            self.stress    = data.get("stress", 0.0)
            self.total_clicks = data.get("total_clicks", 0)

            # Si pasó mucho tiempo desde la última sesión, te extrañó
            elapsed = time.time() - data.get("last_seen", time.time())
            if elapsed > 3600 * 6:  # 6 horas
                self.affection = max(0, self.affection - 20)
                QTimer.singleShot(2000, self._greet_return)
            self.update_sprite()
        except Exception:
            pass

    def save_state(self):
        data = {
            "x":         self.x(),
            "y":         self.y(),
            "energy":    self.energy,
            "direction": self.direction,
            "hunger":    self.hunger,
            "boredom":   self.boredom,
            "affection": self.affection,
            "stress":    self.stress,
            "total_clicks": self.total_clicks,
            "last_seen": time.time(),
        }
        try:
            with open(_save_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _greet_return(self):
        self._interrupt("front", 4)
        self.bubble.say(random.choice([
            "¡Volviste! 😻", "Te extrañé...", "¿Dónde estabas?",
            "¡Miau! ¡Hola!"
        ]), ms=4000)
        self.position_bubble()

    # ------------------------------------------------------------------ brain
    def tick_brain(self):
        """Metabolismo emocional: corre cada 5s."""
        now = time.time()
        dt  = 5.0

        # Hambre sube con el tiempo
        self.hunger = min(100, self.hunger + dt * 0.15)

        # Aburrimiento sube si no interactúas
        since = now - self.last_interaction
        if since > 60:
            self.boredom = min(100, self.boredom + dt * 0.3)
        else:
            self.boredom = max(0, self.boredom - dt * 0.5)

        # Estrés baja si lo dejas tranquilo
        self.stress = max(0, self.stress - dt * 0.2)

        # Afecto decae lentamente si no lo tocas
        if since > 300:
            self.affection = max(0, self.affection - dt * 0.1)

        # Si tiene mucha hambre, se queja
        if self.hunger > 80 and random.random() < 0.3:
            self.bubble.say(random.choice([
                "Tengo mucha hambre...", "¿Me das algo?",
                "Miau... comida...", "Estómago vacío 😿"
            ]), ms=3000)
            self.position_bubble()

    def tick_user_activity(self):
        """Detecta si el usuario está activo por movimiento del mouse."""
        pos = QCursor.pos()
        if pos != self._last_mouse:
            self.user_idle_seconds = 0
            self._last_mouse = pos
        else:
            self.user_idle_seconds += 5

    # ------------------------------------------------------------------ mood
    @property
    def mood(self):
        if self.stress > 60:
            return "tired"
        if self.hunger > 75:
            return "normal"
        if self.energy < 25:
            return "tired"
        if self.affection > 70 and self.energy > 60:
            return "happy"
        if self.boredom > 60 and self.energy > 50:
            return "playful"
        return "normal"

    def pick_phrase(self):
        from datetime import datetime
        now = datetime.now()

        # Prioridades contextuales
        if self.user_idle_seconds > 300:
            return random.choice(PHRASES["lonely"])
        if self.hunger > 70:
            return random.choice(PHRASES["hungry"])
        if self.stress > 60:
            return random.choice(PHRASES["stressed"])

        if self.senses.is_late():
            pool = PHRASES["late"] + PHRASES["normal"]
        elif 6 <= now.hour < 10:
            pool = PHRASES["morning"] + PHRASES[self.mood]
        else:
            pool = PHRASES.get(self.mood, PHRASES["normal"])
        return random.choice(pool)

    # ------------------------------------------------------------------ think (Utility AI)
    def think(self):
        self.ticks_in_state += 1
        if self.ticks_in_state < self.state_duration:
            return
        self.ticks_in_state = 0
        prev = self.state

        if self.follow_active or self.state == "pounce":
            return

        # -------- Evaluar utilidad de cada acción --------
        options = {}

        # Dormir: útil si energía baja, inútil si hay hambre
        options["sleep"] = max(0, (40 - self.energy)) + self.stress * 0.3

        # Pedir comida: útil si hambre alta
        options["beg_food"] = self.hunger * 1.2

        # Jugar (follow/pounce): útil si aburrido y con energía
        options["play"] = (self.boredom * 0.8) + (self.energy * 0.3) + (self.affection * 0.2)

        # Buscar atención: útil si afecto bajo o aburrido
        options["seek_attention"] = (100 - self.affection) * 0.9 + self.boredom * 0.4

        # Pasear: siempre disponible como fallback
        options["wander"] = 25 + self.energy * 0.1

        # Aseo: útil si estrés alto
        options["groom"] = self.stress * 1.5 + 10

        # Si el usuario está idle mucho tiempo, baja el deseo de interactuar
        if self.user_idle_seconds > 120:
            options["play"]           *= 0.2
            options["seek_attention"] *= 0.3
            options["sleep"]          += 20

        # Elegir la mejor opción con algo de ruido
        action = max(options, key=lambda k: options[k] + random.uniform(-8, 8))

        # -------- Ejecutar la acción elegida --------
        if action == "sleep":
            self._enter_state("sleep", random.randint(5, 10))
            if prev != "sleep":
                self.bubble.say(random.choice(["Zzz...", "Mmm...", "Zz..."]), ms=2500)
                self.position_bubble()

        elif action == "beg_food":
            self._enter_state("front", 4)
            self.bubble.say(random.choice([
                "¡Miau! ¡Comida!", "Tengo hambre 🍣",
                "¿Ya es hora de comer?", "Miau miau..."
            ]), ms=3500)
            self.position_bubble()

        elif action == "play":
            if random.random() < 0.6:
                self._start_follow()
            else:
                self._do_pounce()
            return

        elif action == "seek_attention":
            self._enter_state("front", random.randint(3, 6))
            self.bubble.say(self.pick_phrase(), ms=3000)
            self.position_bubble()

        elif action == "groom":
            self._enter_state(random.choice(["clean", "stretch"]), random.randint(2, 4))
            self.bubble.say(random.choice(["Limpiándome~", "Ahhh...", "Relajado."]), ms=2000)
            self.position_bubble()

        else:  # wander
            s = random.choice(["walk", "walk", "run"])
            self._enter_state(s, random.randint(4, 8))
            self.direction = random.choice([-1, 1])
            self.dy        = random.choice([-1, 0, 1])
            self.speed     = 2 if s == "walk" else 4

    def _enter_state(self, state, duration):
        self.state          = state
        self.state_duration = duration
        self.frame_index    = 0
        if state == "sleep":
            self.sleep_frame = random.randint(0, len(self.frames["sleep"]) - 1)
            self.frame_index = self.sleep_frame
        self.update_sprite()

    # ------------------------------------------------------------------ acciones
    def feed(self):
        """Alimenta al gato desde el tray."""
        self.hunger = max(0, self.hunger - 60)
        self.affection = min(100, self.affection + 10)
        self.boredom = max(0, self.boredom - 15)
        self.last_fed = time.time()
        self._interrupt("front", 3)
        self.bubble.say(random.choice([
            "¡Ñam ñam! 😻", "¡Gracias!", "¡Delicioso!",
            "Miau~ ¡rico!"
        ]), ms=3000)
        self.position_bubble()

    def pet_me(self):
        """Acaricia al gato desde el tray."""
        self.affection = min(100, self.affection + 15)
        self.stress = max(0, self.stress - 20)
        self.boredom = max(0, self.boredom - 10)
        self.last_interaction = time.time()
        self._interrupt("meow", 2)
        self.bubble.say(random.choice([
            "¡Miau~! 💕", "Purrr...", "¡Más!",
            "Me gusta 😸", "Rrrrr..."
        ]), ms=2500)
        self.position_bubble()

    # ------------------------------------------------------------------ follow
    def _start_follow(self):
        self.follow_active = True
        self.state         = "run"
        self.speed         = 4
        self.frame_index   = 0
        self.update_sprite()
        self.bubble.say(random.choice(["¡Espérame!", "¡Te sigo!", "Miau~"]), ms=2000)
        self.position_bubble()
        secs = random.randint(4, 8)
        self.follow_timer.start(secs * 1000)

    def _stop_follow(self):
        self.follow_active = False
        self.follow_timer.stop()
        self._enter_state("idle", random.randint(2, 4))

    def _tick_follow(self):
        mouse = QCursor.pos()
        cx    = self.x() + BOX // 2
        cy    = self.y() + BOX // 2
        dx    = mouse.x() - cx
        dy    = mouse.y() - cy
        dist  = (dx**2 + dy**2) ** 0.5

        if dist < 20:
            self.state = "idle"
            self.update_sprite()
            return

        self.state = "run"
        step = min(self.speed, dist)
        nx   = self.x() + int(dx / dist * step)
        ny   = self.y() + int(dy / dist * step)
        self.direction = 1 if dx > 0 else -1
        self.move(nx, ny)
        self.update_sprite()

    # ------------------------------------------------------------------ pounce
    def _do_pounce(self):
        mouse          = QCursor.pos()
        self.pounce_target = QPoint(mouse.x() - BOX // 2, mouse.y() - BOX // 2)
        self.direction = 1 if mouse.x() > self.x() + BOX // 2 else -1

        self.state         = "run"
        self.speed         = 7
        self.frame_index   = 0
        self.pounce_steps  = 0
        self.update_sprite()

        QTimer.singleShot(600, self._finish_pounce)

    def _finish_pounce(self):
        if self.pounce_target:
            self.move(self.pounce_target)
        self._enter_state("pounce", 2)
        self.bubble.say(random.choice(["¡Boo!", "¡Miau!", "¡Te atrapé!"]), ms=1800)
        self.position_bubble()
        self.pounce_target = None
        QTimer.singleShot(800, lambda: self._enter_state("idle", random.randint(2, 4)))

    # ------------------------------------------------------------------ flee
    def _flee_from_cursor(self):
        """Si el cursor se acerca y el gato está estresado, huye."""
        mouse = QCursor.pos()
        cx = self.x() + BOX // 2
        cy = self.y() + BOX // 2
        dx = cx - mouse.x()
        dy = cy - mouse.y()
        dist = (dx**2 + dy**2) ** 0.5
        if 0 < dist < 150:
            self.direction = 1 if dx > 0 else -1
            nx = self.x() + int(dx / dist * 6)
            ny = self.y() + int(dy / dist * 6)
            self.move(nx, ny)
            self.state = "run"
            self.frame_index = 0
            self.update_sprite()

    # ------------------------------------------------------------------ move
    def tick_move(self):
        screen = self.screen().availableGeometry()

        # Huida si está estresado y el cursor se acerca
        if self.stress > 50 and not self.follow_active and self.drag_pos is None:
            self._flee_from_cursor()
            self._clamp_to_screen(screen)
            return

        if self.follow_active:
            self._tick_follow()
            self._clamp_to_screen(screen)
            return

        if self.state in ("walk", "run") and self.drag_pos is None:
            spd_x = self._soft_speed_x(screen)
            spd_y = self._soft_speed_y(screen)
            self.move(self.x() + self.direction * spd_x,
                      self.y() + self.dy * spd_y)
            cost = 0.3 if self.state == "walk" else 0.8
            self.energy = max(0, self.energy - cost)
            self.hunger = min(100, self.hunger + 0.05)
        else:
            if self.state == "sleep":
                self.energy = min(100, self.energy + 1.2)
            elif self.state == "idle":
                self.energy = min(100, self.energy + 0.2)
            elif self.state in ("clean", "stretch"):
                self.energy = min(100, self.energy + 0.4)

        self._clamp_to_screen(screen)

    def _soft_speed_x(self, screen):
        if self.direction == 1:
            dist = screen.right() - (self.x() + self.width())
        else:
            dist = self.x() - screen.left()
        return self._dampen(self.speed, dist)

    def _soft_speed_y(self, screen):
        if self.dy == 1:
            dist = screen.bottom() - (self.y() + self.height())
        elif self.dy == -1:
            dist = self.y() - screen.top()
        else:
            return 0
        return self._dampen(self.speed, dist)

    def _dampen(self, spd, dist):
        if dist <= 0:              return 0
        if dist >= self.BORDER_MARGIN: return spd
        return max(1, int(spd * dist / self.BORDER_MARGIN))

    def _clamp_to_screen(self, screen):
        if self.x() <= screen.left():
            self.direction = 1
            self.move(screen.left(), self.y())
        elif self.x() + self.width() >= screen.right():
            self.direction = -1
            self.move(screen.right() - self.width(), self.y())

        if self.y() <= screen.top():
            self.dy = 1
            self.move(self.x(), screen.top())
        elif self.y() + self.height() >= screen.bottom():
            self.dy = -1
            self.move(self.x(), screen.bottom() - self.height())

    # ------------------------------------------------------------------ anim
    def tick_anim(self):
        if self.state == "sleep":
            self.frame_index = self.sleep_frame
        else:
            self.frame_index = (self.frame_index + 1) % len(self.frames[self.state])
        self.update_sprite()

    def update_sprite(self):
        frame, flipped = self.frames[self.state][self.frame_index]
        self.sprite.setPixmap(frame if self.direction == 1 else flipped)
        self.setWindowOpacity(0.5 if self.state == "sleep" else 1.0)

    # ------------------------------------------------------------------ look
    def look_at_mouse(self):
        if self.state not in ("idle", "front", "clean", "stretch"):
            return
        mouse = QCursor.pos()
        self.direction = 1 if mouse.x() >= self.x() + BOX // 2 else -1
        self.update_sprite()

    # ------------------------------------------------------------------ bubble
    def position_bubble(self):
        screen = self.screen().availableGeometry()
        bw, bh = self.bubble.width(), self.bubble.height()
        bx = self.x() + BOX // 2 - bw // 2
        by = self.y() - bh + 5
        if by < screen.top():
            by = self.y() + BOX - 5
        bx = max(screen.left(), min(bx, screen.right()  - bw))
        by = max(screen.top(),  min(by, screen.bottom() - bh))
        self.bubble.move(bx, by)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.bubble.isVisible():
            self.position_bubble()

    # ------------------------------------------------------------------ react
    def react_to_sense(self, kind, message):
        self._interrupt("meow", 2)
        self.bubble.say(message, ms=3500)
        self.position_bubble()

    def react_to_reminder(self, kind, message):
        self._interrupt("meow", 2)
        self.bubble.say(message, ms=5000)
        self.position_bubble()

    def react_to_inactivity(self):
        phrases = [
            "¿Sigues ahí?", "¿Te dormiste tú también?",
            "Oye... oye.", "¿Hola?", "...", "Psst.",
            "¿Me abandonaste?", "Estoy solo aquí...",
        ]
        self._interrupt("front", 3)
        self.bubble.say(random.choice(phrases), ms=4000)
        self.position_bubble()

    def _interrupt(self, state, duration):
        self.follow_active = False
        self.follow_timer.stop()
        self.state          = state
        self.frame_index    = 0
        self.ticks_in_state = 0
        self.state_duration = duration
        self.update_sprite()

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.last_interaction = time.time()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            self.last_interaction = time.time()
            self.affection = min(100, self.affection + 0.1)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drag_pos is not None:
            offset = (event.globalPosition().toPoint()
                      - self.drag_pos
                      - self.frameGeometry().topLeft())
            if offset.manhattanLength() < 5:
                self.on_click()
        self.drag_pos = None

    def mouseDoubleClickEvent(self, event):
        self._enter_state("sleep", 6)
        self.bubble.say(random.choice(["Zzz...", "Mmm...", "Buenas noches~"]), ms=2500)
        self.position_bubble()

    def contextMenuEvent(self, event):
        mouse = event.globalPos()
        self.direction = 1 if mouse.x() < self.x() else -1
        self.state     = "run"
        self.speed     = 8
        self.dy        = random.choice([-1, 0, 1])
        self.frame_index    = 0
        self.ticks_in_state = 0
        self.state_duration = 3
        self.stress = min(100, self.stress + 20)
        self.affection = max(0, self.affection - 3)
        self.update_sprite()
        self.bubble.say(random.choice(["¡Miau!", "¡Ay!", "¡Asustado!"]), ms=1500)
        self.position_bubble()
        QTimer.singleShot(2500, self.calm_down)
        event.accept()

    def calm_down(self):
        self.speed = 2
        self._enter_state("idle", random.randint(2, 4))

    def on_click(self):
        self.total_clicks += 1
        self.session_clicks += 1
        self.last_interaction = time.time()
        self.affection = min(100, self.affection + 3)
        self.boredom   = max(0, self.boredom - 5)
        self.stress    = max(0, self.stress - 2)

        self._interrupt("meow", 2)
        self.bubble.say(self.pick_phrase(), ms=3000)
        self.position_bubble()