#!/usr/bin/env python3
"""
Пример использования сервисного протокола TechLazer
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ptz.techlazer_service_protocol import TechLazerServiceProtocol


def main():
    """Пример использования сервисного протокола TechLazer"""
    print("Пример использования сервисного протокола TechLazer")
    print("=" * 50)
    
    # Создаем экземпляр контроллера
    controller = TechLazerServiceProtocol(ip="192.168.1.115", port=9760)
    
    try:
        # Подключаемся к устройству
        if controller.connect():
            print("✓ Подключение к сервисному протоколу успешно")
        else:
            print("✗ Не удалось подключиться к сервисному протоколу")
            return
        
        # Получаем информацию о прошивке
        print(f"\nВерсия прошивки: {controller.get_firmware_version()}")
        print(f"Тип прошивки: {controller.get_firmware_type()}")
        
        # Получаем текущие настройки
        print(f"\nАдрес Pelco-D: {controller.get_pelco_address()}")
        print(f"Порт Pelco-D: {controller.get_pelco_port()}")
        print(f"Порт RS-485: {controller.get_rs485_port()}")
        
        # Получаем текущие позиции
        print(f"\nТекущая позиция поворота: {controller.get_current_pan_position():.2f}°")
        print(f"Текущая позиция наклона: {controller.get_current_tilt_position():.2f}°")
        
        # Получаем настройки скоростей
        pan_speeds = controller.get_pan_speed_settings()
        if pan_speeds:
            min_sp, acc_dec, max_sp = pan_speeds
            print(f"\nНастройки скорости поворота:")
            print(f"  Минимальная скорость: {min_sp} °/с")
            print(f"  Ускорение/замедление: {acc_dec} °/с²")
            print(f"  Максимальная скорость: {max_sp} °/с")
        
        tilt_speeds = controller.get_tilt_speed_settings()
        if tilt_speeds:
            min_sp, acc_dec, max_sp = tilt_speeds
            print(f"\nНастройки скорости наклона:")
            print(f"  Минимальная скорость: {min_sp} °/с")
            print(f"  Ускорение/замедление: {acc_dec} °/с²")
            print(f"  Максимальная скорость: {max_sp} °/с")
        
        # Пример движения: перемещение в позицию поворота
        print(f"\nПеремещение в позицию поворота 180.0° со скоростью 20.0 °/с")
        success = controller.move_to_pan_position(180.0, 20.0)
        if success:
            print("✓ Команда перемещения поворота отправлена успешно")
        else:
            print("✗ Ошибка отправки команды перемещения поворота")
        
        # Пример движения: перемещение в позицию наклона
        print(f"\nПеремещение в позицию наклона 45.0° со скоростью 10.0 °/с")
        success = controller.move_to_tilt_position(45.0, 10.0)
        if success:
            print("✓ Команда перемещения наклона отправлена успешно")
        else:
            print("✗ Ошибка отправки команды перемещения наклона")
        
        # Пример получения температуры
        temp = controller.get_current_temperature()
        if temp is not None:
            print(f"\nТекущая температура: {temp:+.1f}°C")
        
        # Пример получения напряжения питания
        voltage = controller.get_supply_voltage()
        if voltage is not None:
            print(f"Напряжение питания: {voltage:.1f} В")
        
        # Пример получения статуса осей
        pan_state = controller.get_pan_axis_state()
        tilt_state = controller.get_tilt_axis_state()
        print(f"\nСостояние оси поворота: {pan_state}")
        print(f"Состояние оси наклона: {tilt_state}")
        
    except Exception as e:
        print(f"Ошибка во время работы: {str(e)}")
    
    finally:
        # Закрываем соединение
        controller.close()
        print("\nСоединение закрыто")


if __name__ == "__main__":
    main()