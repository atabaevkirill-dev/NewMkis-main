#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы сервисного протокола TechLazer
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ptz.techlazer_service_protocol import TechLazerServiceProtocol
import time


def test_basic_connection():
    """Тест базового подключения"""
    print("=== Тест подключения ===")
    controller = TechLazerServiceProtocol(ip="192.168.1.115", port=9760)
    
    if controller.connect():
        print("✓ Подключение успешно установлено")
        controller.disconnect()
        print("✓ Отключение выполнено успешно")
        return True
    else:
        print("✗ Подключение не удалось")
        return False


def test_firmware_commands(controller):
    """Тест команд получения информации о прошивке"""
    print("\n=== Тест команд прошивки ===")
    
    # Получить тип прошивки
    firmware_type = controller.get_firmware_type()
    print(f"Тип прошивки: {firmware_type}")
    
    # Получить версию прошивки
    version = controller.get_firmware_version()
    print(f"Версия прошивки: {version}")
    
    return True


def test_pelco_commands(controller):
    """Тест команд Pelco-D"""
    print("\n=== Тест команд Pelco-D ===")
    
    # Получить адрес Pelco-D
    addr = controller.get_pelco_address()
    print(f"Адрес Pelco-D: {addr}")
    
    # Задать адрес Pelco-D (если нужно)
    # controller.set_pelco_address(201)
    
    # Получить порт Pelco-D
    port = controller.get_pelco_port()
    print(f"Порт Pelco-D: {port}")
    
    # Получить порт RS-485
    rs485_port = controller.get_rs485_port()
    print(f"Порт RS-485: {rs485_port}")
    
    return True


def test_speed_settings(controller):
    """Тест настроек скоростей"""
    print("\n=== Тест настроек скоростей ===")
    
    # Получить настройки скорости поворота
    pan_speeds = controller.get_pan_speed_settings()
    print(f"Настройки скорости поворота: {pan_speeds}")
    
    # Получить настройки скорости наклона
    tilt_speeds = controller.get_tilt_speed_settings()
    print(f"Настройки скорости наклона: {tilt_speeds}")
    
    return True


def test_position_commands(controller):
    """Тест команд позиционирования"""
    print("\n=== Тест команд позиционирования ===")
    
    # Получить текущую позицию поворота
    pan_pos = controller.get_current_pan_position()
    print(f"Текущая позиция поворота: {pan_pos}")
    
    # Получить текущую позицию наклона
    tilt_pos = controller.get_current_tilt_position()
    print(f"Текущая позиция наклона: {tilt_pos}")
    
    # Получить целевую позицию поворота
    target_pan = controller.get_target_pan_position_and_max_speed()
    print(f"Целевая позиция поворота: {target_pan}")
    
    # Получить целевую позицию наклона
    target_tilt = controller.get_target_tilt_position_and_max_speed()
    print(f"Целевая позиция наклона: {target_tilt}")
    
    return True


def main():
    """Основная функция тестирования"""
    print("Тестирование сервисного протокола TechLazer")
    print("=" * 50)
    
    # Тест подключения
    if not test_basic_connection():
        print("Тест подключения не пройден, завершаем тестирование")
        return
    
    # Создаем контроллер для дальнейших тестов
    controller = TechLazerServiceProtocol(ip="192.168.1.115", port=9760)
    
    if not controller.connect():
        print("Не удалось подключиться для выполнения расширенных тестов")
        return
    
    try:
        # Тест команд прошивки
        test_firmware_commands(controller)
        
        # Тест команд Pelco-D
        test_pelco_commands(controller)
        
        # Тест настроек скоростей
        test_speed_settings(controller)
        
        # Тест команд позиционирования
        test_position_commands(controller)
        
    finally:
        controller.close()
        print("\nТестирование завершено")


if __name__ == "__main__":
    main()