import sys
from PySide6.QtWidgets import QApplication
from pet import Pet


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)  # no cerrar al ocultar

pet = Pet()
pet.show()

# Guardar al salir
app.aboutToQuit.connect(pet.save_state)

sys.exit(app.exec())