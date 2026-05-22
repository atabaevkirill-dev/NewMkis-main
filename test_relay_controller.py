import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from relayx3.pelco_d_controller import PelcoDController
from PyQt6.QtWidgets import QApplication

def main():
    app = QApplication(sys.argv)
    
    controller = PelcoDController()
    controller.setWindowTitle("Тестирование Pelco-D контроллера")
    controller.resize(800, 900)
    controller.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()