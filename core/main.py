#!/usr/bin/env python
import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    # Set a timer to force exit if the app doesn't close gracefully within 5 seconds
    def force_exit():
        sys.exit(0)
        
    from PyQt6.QtCore import QTimer
    exit_timer = QTimer()
    exit_timer.setSingleShot(True)
    exit_timer.timeout.connect(force_exit)
    exit_timer.setInterval(5000)  # 5 seconds
    
    # Connect to the aboutToQuit signal
    app.aboutToQuit.connect(exit_timer.start)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()