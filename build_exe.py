import subprocess
import sys

def build_executable():
    """
    Скрипт для упаковки Python-приложения в автономный исполняемый файл с помощью PyInstaller
    """
    print("Начинаем процесс упаковки приложения...")
    
    # Устанавливаем зависимости проекта, если они не установлены
    print("Проверяем зависимости...")
    try:
        import PyQt6
        import cv2
        import numpy as np
        import onvif
        import zeep
        import serial  # Проверяем также serial
    except ImportError as e:
        print(f"Устанавливаем зависимости... Ошибка: {e}")
        subprocess.check_call([sys.executable, "install_requirements.py"])
    
    # Запускаем PyInstaller с файлом спецификации
    print("Запускаем PyInstaller...")
    try:
        result = subprocess.run([
            sys.executable, 
            "-m", 
            "PyInstaller", 
            "oncam_app.spec"
        ], check=True, capture_output=True, text=True)
        
        print("Выходной код:", result.returncode)
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        print("Приложение успешно упаковано!")
        print("Исполняемый файл находится в папке 'dist' проекта")
        
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении PyInstaller: {e}")
        print(f"STDERR: {e.stderr}")
        return False
    except FileNotFoundError:
        print("PyInstaller не установлен. Устанавливаем...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller установлен, повторяем сборку...")
        build_executable()
    
    return True
