import sys
from PyQt6.QtWidgets import QApplication
from pelco_d_controller import PelcoDController

def main():
    app = QApplication(sys.argv)
    
    controller = PelcoDController()
    controller.setWindowTitle("Тестирование Pelco-D контроллера")
    controller.resize(800, 900)
    controller.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()