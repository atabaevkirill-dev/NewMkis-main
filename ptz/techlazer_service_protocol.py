import socket
import threading
import time
import logging
from typing import Optional, Tuple, Dict, Any


class TechLazerServiceProtocol:
    """
    Класс для работы с сервисным протоколом TechLazer на порту 9760
    """
    
    def __init__(self, ip: str = "192.168.1.115", port: int = 9760):
        self.ip = ip
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.lock = threading.Lock()  # Для потокобезопасности
        
        # Настройка логирования
        self.logger = logging.getLogger(__name__)
        
    def connect(self) -> bool:
        """
        Подключение к устройству через сервисный протокол
        """
        try:
            self.disconnect()  # Отключаемся, если уже подключены
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)  # Таймаут 5 секунд
            self.socket.connect((self.ip, self.port))
            
            self.connected = True
            self.logger.info(f"Successfully connected to TechLazer service protocol at {self.ip}:{self.port}")
            return True
            
        except Exception as e:
            self.connected = False
            self.logger.error(f"Failed to connect to TechLazer service protocol at {self.ip}:{self.port}, error: {str(e)}")
            return False
    
    def disconnect(self):
        """
        Отключение от устройства
        """
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                self.logger.warning(f"Error closing socket: {str(e)}")
            finally:
                self.socket = None
                self.connected = False
    
    def _send_command(self, command: str) -> Optional[str]:
        """
        Отправка команды и получение ответа
        """
        if not self.connected or not self.socket:
            if not self.connect():
                return None
        
        with self.lock:  # Потокобезопасность
            try:
                # Отправляем команду
                self.socket.sendall(command.encode('utf-8'))
                
                # Ждем ответ
                response = b""
                self.socket.settimeout(5)  # Таймаут ожидания ответа
                
                while True:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    
                    # Проверяем завершение ответа (обычно заканчивается символом #)
                    if b'#' in chunk:
                        break
                
                response_str = response.decode('utf-8', errors='ignore').strip()
                self.logger.debug(f"Command: {command} -> Response: {response_str}")
                return response_str
                
            except Exception as e:
                self.logger.error(f"Error sending command '{command}': {str(e)}")
                self.connected = False
                # Попробуем переподключиться
                self.connect()
                return None
    
    def get_firmware_type(self) -> Optional[str]:
        """
        Получить тип прошивки
        Команда: $I#
        Ответ: $Io#
        """
        response = self._send_command("$I#")
        return response if response and response.startswith("$Io#") else None
    
    def get_firmware_version(self) -> Optional[float]:
        """
        Получить версию прошивки
        Команда: $V#
        Ответ: $Vxxxx# где xxxx – версия по формату %04x, делится на 100
        Пример: $V0074# -> 0x0074 = 116 -> 1.16
        """
        response = self._send_command("$V#")
        if response and response.startswith("$V") and response.endswith("#"):
            try:
                # Извлекаем hex часть (между $V и #)
                hex_part = response[2:-1]  # Убираем $V и #
                if len(hex_part) == 4 and hex_part.isdigit():
                    version_int = int(hex_part, 16)
                    version_float = version_int / 100.0
                    return version_float
            except ValueError:
                pass
        return None
    
    def get_pelco_address(self) -> Optional[int]:
        """
        Получить адрес для протокола Pelco-D
        Команда: $1#
        Ответ: $1,addr# где addr от 0 до 255
        """
        response = self._send_command("$1#")
        if response and response.startswith("$1,") and response.endswith("#"):
            try:
                addr_str = response[3:-1]  # Убираем $1, и #
                addr = int(addr_str)
                return addr if 0 <= addr <= 255 else None
            except ValueError:
                pass
        return None
    
    def set_pelco_address(self, address: int) -> bool:
        """
        Задать адрес для протокола Pelco-D
        Команда: $1,addr# где addr от 0 до 255
        """
        if not (0 <= address <= 255):
            self.logger.error("Address must be between 0 and 255")
            return False
        
        command = f"$1,{address}#"
        response = self._send_command(command)
        return response is not None
    
    def get_rs485_baud_rate(self) -> Optional[int]:
        """
        Получить скорость порта RS-485
        Команда: $2#
        Ответ: $2,baud# где baud может быть 1-8 (1200, 2400, 3600, 4800, 9600, 19200, 38400, 115200)
        """
        response = self._send_command("$2#")
        if response and response.startswith("$2,") and response.endswith("#"):
            try:
                baud_code_str = response[3:-1]  # Убираем $2, и #
                baud_code = int(baud_code_str)
                
                # Соответствие кодов скоростям
                baud_rates = {
                    1: 1200,
                    2: 2400,
                    3: 3600,
                    4: 4800,
                    5: 9600,
                    6: 19200,
                    7: 38400,
                    8: 115200
                }
                
                return baud_rates.get(baud_code)
            except ValueError:
                pass
        return None
    
    def set_rs485_baud_rate(self, baud_rate: int) -> bool:
        """
        Задать скорость порта RS-485
        Команда: $2,baud# где baud код скорости (1-8)
        """
        baud_codes = {
            1200: 1, 2400: 2, 3600: 3, 4800: 4,
            9600: 5, 19200: 6, 38400: 7, 115200: 8
        }
        
        if baud_rate not in baud_codes:
            self.logger.error(f"Baud rate {baud_rate} not supported. Supported: {list(baud_codes.keys())}")
            return False
        
        baud_code = baud_codes[baud_rate]
        command = f"$2,{baud_code}#"
        response = self._send_command(command)
        return response is not None
    
    def get_pan_speed_settings(self) -> Optional[Tuple[float, float, float]]:
        """
        Получить скорости для оси поворота (pan)
        Команда: $3#
        Ответ: $3,min,accDec,max# 
        где min - минимальная скорость °/с (0.00-50.00)
        accDec - ускорение разгона/торможения °/с2 (1.00-50.00) 
        max - максимальная скорость °/с (3.00-50.00)
        """
        response = self._send_command("$3#")
        if response and response.startswith("$3,") and response.endswith("#"):
            try:
                # Убираем $3 и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 3:
                    min_speed = float(values[0])
                    acc_dec = float(values[1])
                    max_speed = float(values[2])
                    
                    return min_speed, acc_dec, max_speed
            except ValueError:
                pass
        return None
    
    def set_pan_speed_settings(self, min_speed: float, acc_dec: float, max_speed: float) -> bool:
        """
        Задать скорости для оси поворота (pan)
        Команда: $3,min,accDec,max#
        """
        if not (0.00 <= min_speed <= 50.00):
            self.logger.error("Min speed must be between 0.00 and 50.00 °/s")
            return False
        if not (1.00 <= acc_dec <= 50.00):
            self.logger.error("Acceleration/Deceleration must be between 1.00 and 50.00 °/s²")
            return False
        if not (3.00 <= max_speed <= 50.00):
            self.logger.error("Max speed must be between 3.00 and 50.00 °/s")
            return False
        
        command = f"$3,{min_speed:.2f},{acc_dec:.2f},{max_speed:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_tilt_speed_settings(self) -> Optional[Tuple[float, float, float]]:
        """
        Получить скорости для оси наклона (tilt)
        Команда: $4#
        Ответ: $4,min,accDec,max#
        где min - минимальная скорость °/с (0.00-17.00)
        accDec - ускорение разгона/торможения °/с2 (1.00-17.00)
        max - максимальная скорость °/с (3.00-19.00)
        """
        response = self._send_command("$4#")
        if response and response.startswith("$4,") and response.endswith("#"):
            try:
                # Убираем $4 и #, разбиваем по запятым
                values_str = response[4:-1]
                values = values_str.split(',')
                
                if len(values) == 3:
                    min_speed = float(values[0])
                    acc_dec = float(values[1])
                    max_speed = float(values[2])
                    
                    return min_speed, acc_dec, max_speed
            except ValueError:
                pass
        return None
    
    def set_tilt_speed_settings(self, min_speed: float, acc_dec: float, max_speed: float) -> bool:
        """
        Задать скорости для оси наклона (tilt)
        Команда: $4,min,accDec,max#
        """
        if not (0.00 <= min_speed <= 17.00):
            self.logger.error("Min speed must be between 0.00 and 17.00 °/s")
            return False
        if not (1.00 <= acc_dec <= 17.00):
            self.logger.error("Acceleration/Deceleration must be between 1.00 and 17.00 °/s²")
            return False
        if not (3.00 <= max_speed <= 19.00):
            self.logger.error("Max speed must be between 3.00 and 19.00 °/s")
            return False
        
        command = f"$4,{min_speed:.2f},{acc_dec:.2f},{max_speed:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_pan_limits(self) -> Optional[Tuple[bool, float, float]]:
        """
        Получить ограничения для оси поворота (pan)
        Команда: $7#
        Ответ: $7,enable,left,right#
        где enable - флаг включения ограничения (0 или 1)
        left - ограничение слева (180.50-359.99)
        right - ограничение справа (0.00-179.50)
        """
        response = self._send_command("$7#")
        if response and response.startswith("$7,") and response.endswith("#"):
            try:
                # Убираем $7 и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 3:
                    enable = values[0] == '1'
                    left = float(values[1])
                    right = float(values[2])
                    
                    return enable, left, right
            except ValueError:
                pass
        return None
    
    def set_pan_limits(self, enable: bool, left: float, right: float) -> bool:
        """
        Задать ограничения для оси поворота (pan)
        Команда: $7,enable,left,right#
        """
        if not (left >= 180.50 and left <= 359.99):
            self.logger.error("Left limit must be between 180.50 and 359.99 degrees")
            return False
        if not (right >= 0.00 and right <= 179.50):
            self.logger.error("Right limit must be between 0.00 and 179.50 degrees")
            return False
        
        enable_val = 1 if enable else 0
        command = f"$7,{enable_val},{left:.2f},{right:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_tilt_limits(self) -> Optional[Tuple[float, float]]:
        """
        Получить ограничения для оси наклона (tilt)
        Команда: $8#
        Ответ: $8,left,right#
        где left - ограничение слева (315.00-359.99)
        right - ограничение справа (0.00-90.00)
        """
        response = self._send_command("$8#")
        if response and response.startswith("$8,") and response.endswith("#"):
            try:
                # Убираем $8 и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 2:
                    left = float(values[0])
                    right = float(values[1])
                    
                    return left, right
            except ValueError:
                pass
        return None
    
    def set_tilt_limits(self, left: float, right: float) -> bool:
        """
        Задать ограничения для оси наклона (tilt)
        Команда: $8,left,right#
        """
        if not (left >= 315.00 and left <= 359.99):
            self.logger.error("Left limit must be between 315.00 and 359.99 degrees")
            return False
        if not (right >= 0.00 and right <= 90.00):
            self.logger.error("Right limit must be between 0.00 and 90.00 degrees")
            return False
        
        command = f"$8,{left:.2f},{right:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_heater_settings(self) -> Optional[Tuple[bool, float, float]]:
        """
        Получить настройки обогрева
        Команда: $9#
        Ответ: $9,enable,off,on#
        где enable - флаг включения алгоритма автоматического обогрева (0 или 1)
        off - температура выключения обогрева (-100.0 до 100.0)
        on - температура включения обогрева (-100.0 до 100.0)
        """
        response = self._send_command("$9#")
        if response and response.startswith("$9,") and response.endswith("#"):
            try:
                # Убираем $9 и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 3:
                    enable = values[0] == '1'
                    off_temp = float(values[1])
                    on_temp = float(values[2])
                    
                    return enable, off_temp, on_temp
            except ValueError:
                pass
        return None
    
    def set_heater_settings(self, enable: bool, off_temp: float, on_temp: float) -> bool:
        """
        Задать настройки обогрева
        Команда: $9,enable,off,on#
        Температура включения должна быть меньше температуры выключения
        """
        if on_temp >= off_temp:
            self.logger.error("On temperature must be less than off temperature")
            return False
        if not (-100.0 <= off_temp <= 100.0):
            self.logger.error("Off temperature must be between -100.0 and 100.0")
            return False
        if not (-100.0 <= on_temp <= 100.0):
            self.logger.error("On temperature must be between -100.0 and 100.0")
            return False
        
        enable_val = 1 if enable else 0
        command = f"$9,{enable_val},{off_temp:.1f},{on_temp:.1f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_network_settings(self) -> Optional[Dict[str, Any]]:
        """
        Получить настройки сети
        Команда: $a#
        Ответ: $a,dhcp,ip,mask,gateway,dns#
        """
        response = self._send_command("$a#")
        if response and response.startswith("$a,") and response.endswith("#"):
            try:
                # Убираем $a и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 5:
                    dhcp = values[0] == '1'
                    ip = values[1]
                    mask = values[2]
                    gateway = values[3]
                    dns = values[4]
                    
                    return {
                        'dhcp': dhcp,
                        'ip': ip,
                        'mask': mask,
                        'gateway': gateway,
                        'dns': dns
                    }
            except ValueError:
                pass
        return None
    
    def set_network_settings(self, dhcp: bool, ip: str, mask: str, gateway: str, dns: str) -> bool:
        """
        Задать настройки сети
        Команда: $a,dhcp,ip,mask,gateway,dns#
        """
        dhcp_val = 1 if dhcp else 0
        command = f"$a,{dhcp_val},{ip},{mask},{gateway},{dns}#"
        response = self._send_command(command)
        return response is not None
    
    def get_pelco_port(self) -> Optional[int]:
        """
        Получить номер TCP порта Pelco-D
        Команда: $b#
        Ответ: $b,port# где порт от 0 до 65535
        """
        response = self._send_command("$b#")
        if response and response.startswith("$b,") and response.endswith("#"):
            try:
                port_str = response[3:-1]  # Убираем $b, и #
                port = int(port_str)
                return port if 0 <= port <= 65535 else None
            except ValueError:
                pass
        return None
    
    def set_pelco_port(self, port: int) -> bool:
        """
        Задать номер TCP порта Pelco-D
        Команда: $b,port#
        """
        if not (0 <= port <= 65535):
            self.logger.error("Port must be between 0 and 65535")
            return False
        
        command = f"$b,{port}#"
        response = self._send_command(command)
        return response is not None
    
    def get_rs485_port(self) -> Optional[int]:
        """
        Получить номер TCP порта RS-485
        Команда: $c#
        Ответ: $c,port# где порт от 0 до 65535
        """
        response = self._send_command("$c#")
        if response and response.startswith("$c,") and response.endswith("#"):
            try:
                port_str = response[3:-1]  # Убираем $c, и #
                port = int(port_str)
                return port if 0 <= port <= 65535 else None
            except ValueError:
                pass
        return None
    
    def set_rs485_port(self, port: int) -> bool:
        """
        Задать номер TCP порта RS-485
        Команда: $c,port#
        """
        if not (0 <= port <= 65535):
            self.logger.error("Port must be between 0 and 65535")
            return False
        
        command = f"$c,{port}#"
        response = self._send_command(command)
        return response is not None
    
    def factory_reset(self) -> bool:
        """
        Удаленный сброс настроек в заводские
        Команда: $d#
        """
        response = self._send_command("$d#")
        return response is not None
    
    def reboot_device(self) -> bool:
        """
        Удаленная перезагрузка устройства
        Команда: $e#
        """
        response = self._send_command("$e#")
        return response is not None
    
    def get_heater_status(self) -> Optional[str]:
        """
        Получить статус активности обогрева
        Команда: $h#
        Ответ: $hX# где X может быть E (включен) или D (выключен)
        """
        response = self._send_command("$h#")
        if response and response.startswith("$h") and response.endswith("#"):
            try:
                status_char = response[2]  # Буква между $h и #
                if status_char in ['E', 'D']:
                    return status_char
            except IndexError:
                pass
        return None
    
    def enable_heater_manual(self) -> bool:
        """
        Включить обогрев вручную при отключенном алгоритме автоматического обогрева
        Команда: $hE#
        """
        response = self._send_command("$hE#")
        return response is not None
    
    def disable_heater_manual(self) -> bool:
        """
        Выключить обогрев вручную при отключенном алгоритме автоматического обогрева
        Команда: $hD#
        """
        response = self._send_command("$hD#")
        return response is not None
    
    def get_current_temperature(self) -> Optional[float]:
        """
        Получить текущую температуру
        Команда: $t#
        Ответ: $t,temp# где temp температура в градусах Цельсия, формат "%+.1f"
        """
        response = self._send_command("$t#")
        if response and response.startswith("$t,") and response.endswith("#"):
            try:
                temp_str = response[3:-1]  # Убираем $t, и #
                temp = float(temp_str)
                return temp
            except ValueError:
                pass
        return None
    
    def get_pan_axis_state(self) -> Optional[int]:
        """
        Получить состояние оси поворота
        Команда: $m#
        Ответ: $m,initState# где initState: 0-Не готов, 1-Самодиагностика, 2-Готов
        """
        response = self._send_command("$m#")
        if response and response.startswith("$m,") and response.endswith("#"):
            try:
                state_str = response[3:-1]  # Убираем $m, и #
                state = int(state_str)
                return state
            except ValueError:
                pass
        return None
    
    def start_pan_self_test(self) -> bool:
        """
        Начать процесс самодиагностики оси поворота
        Команда: $m,1#
        """
        response = self._send_command("$m,1#")
        return response is not None
    
    def get_pan_fault_flags(self) -> Optional[str]:
        """
        Получить флаги ошибок оси поворота
        Команда: $n#
        Ответ: $n,faults# где faults - 32-битное шестнадцатеричное число
        """
        response = self._send_command("$n#")
        if response and response.startswith("$n,") and response.endswith("#"):
            try:
                faults_str = response[3:-1]  # Убираем $n, и #
                # Проверяем, что это шестнадцатеричное число
                int(faults_str, 16)
                return faults_str
            except ValueError:
                pass
        return None
    
    def get_current_pan_position(self) -> Optional[float]:
        """
        Получить текущую позицию оси поворота
        Команда: $o#
        Ответ: $o,curPos# где curPos - позиция в ° от 0.00 до 359.99
        """
        response = self._send_command("$o#")
        if response and response.startswith("$o,") and response.endswith("#"):
            try:
                pos_str = response[3:-1]  # Убираем $o, и #
                pos = float(pos_str)
                return pos if 0.00 <= pos <= 359.99 else None
            except ValueError:
                pass
        return None
    
    def get_current_pan_speed(self) -> Optional[float]:
        """
        Получить текущую скорость оси поворота
        Команда: $p#
        Ответ: $p,curSpeed# где curSpeed - скорость в °/c
        Положительное значение - по часовой стрелке, отрицательное - против
        """
        response = self._send_command("$p#")
        if response and response.startswith("$p,") and response.endswith("#"):
            try:
                speed_str = response[3:-1]  # Убираем $p, и #
                speed = float(speed_str)
                return speed
            except ValueError:
                pass
        return None
    
    def get_pan_busy_status(self) -> Optional[int]:
        """
        Получить статус занятости оси поворота
        Команда: $q#
        Ответ: $q,busyStatus# где busyStatus: 0-Удержание, 1-Разгон, 2-Торможение, 3-Равномерное движение
        """
        response = self._send_command("$q#")
        if response and response.startswith("$q,") and response.endswith("#"):
            try:
                status_str = response[3:-1]  # Убираем $q, и #
                status = int(status_str)
                return status
            except ValueError:
                pass
        return None
    
    def get_last_pan_task(self) -> Optional[int]:
        """
        Получить последнюю принятую к исполнению команду оси поворота
        Команда: $s#
        Ответ: $s,lastTask# где lastTask: 0-Нет команд, 1-Самодиагностика, 2-Стоп, 4-Скорость, 5-Позиция
        """
        response = self._send_command("$s#")
        if response and response.startswith("$s,") and response.endswith("#"):
            try:
                task_str = response[3:-1]  # Убираем $s, и #
                task = int(task_str)
                return task
            except ValueError:
                pass
        return None
    
    def stop_pan_axis(self) -> bool:
        """
        Стоп для оси поворота
        Команда: $u#
        """
        response = self._send_command("$u#")
        return response is not None
    
    def get_target_pan_speed(self) -> Optional[float]:
        """
        Получить целевую скорость оси поворота
        Команда: $w#
        Ответ: $w,targetSpeed# где targetSpeed - целевая скорость в °/c
        """
        response = self._send_command("$w#")
        if response and response.startswith("$w,") and response.endswith("#"):
            try:
                speed_str = response[3:-1]  # Убираем $w, и #
                speed = float(speed_str)
                return speed
            except ValueError:
                pass
        return None
    
    def set_pan_speed(self, speed: float) -> bool:
        """
        Задать скорость оси поворота (начать движение)
        Команда: $w,targetSpeed#
        """
        command = f"$w,{speed:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_target_pan_position_and_max_speed(self) -> Optional[Tuple[float, float]]:
        """
        Получить целевую позицию и предельную скорость перехода оси поворота
        Команда: $x#
        Ответ: $x,targetPos,maxSpeed#
        где targetPos - целевая позиция в ° от 0.00 до 359.99
        maxSpeed - предельная скорость при переходе в °/с (всегда положительное)
        """
        response = self._send_command("$x#")
        if response and response.startswith("$x,") and response.endswith("#"):
            try:
                # Убираем $x и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 2:
                    target_pos = float(values[0])
                    max_speed = float(values[1])
                    
                    if 0.00 <= target_pos <= 359.99 and max_speed >= 0:
                        return target_pos, max_speed
            except ValueError:
                pass
        return None
    
    def move_to_pan_position(self, target_pos: float, max_speed: float) -> bool:
        """
        Переход в позицию с заданной скоростью для оси поворота
        Команда: $x,targetPos,maxSpeed#
        """
        if not (0.00 <= target_pos <= 359.99):
            self.logger.error("Target position must be between 0.00 and 359.99 degrees")
            return False
        if max_speed < 0:
            self.logger.error("Max speed must be positive")
            return False
        
        command = f"$x,{target_pos:.2f},{max_speed:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_tilt_axis_state(self) -> Optional[int]:
        """
        Получить состояние оси наклона
        Команда: $M#
        Ответ: $M,initState# где initState: 0-Не готов, 1-Самодиагностика, 2-Готов
        """
        response = self._send_command("$M#")
        if response and response.startswith("$M,") and response.endswith("#"):
            try:
                state_str = response[3:-1]  # Убираем $M, и #
                state = int(state_str)
                return state
            except ValueError:
                pass
        return None
    
    def start_tilt_self_test(self) -> bool:
        """
        Начать процесс самодиагностики оси наклона
        Команда: $M,1#
        """
        response = self._send_command("$M,1#")
        return response is not None
    
    def get_tilt_fault_flags(self) -> Optional[str]:
        """
        Получить флаги ошибок оси наклона
        Команда: $N#
        Ответ: $N,faults# где faults - 32-битное шестнадцатеричное число
        """
        response = self._send_command("$N#")
        if response and response.startswith("$N,") and response.endswith("#"):
            try:
                faults_str = response[3:-1]  # Убираем $N, и #
                # Проверяем, что это шестнадцатеричное число
                int(faults_str, 16)
                return faults_str
            except ValueError:
                pass
        return None
    
    def get_current_tilt_position(self) -> Optional[float]:
        """
        Получить текущую позицию оси наклона
        Команда: $O#
        Ответ: $O,curPos# где curPos - позиция в ° от 0.00 до 359.99
        """
        response = self._send_command("$O#")
        if response and response.startswith("$O,") and response.endswith("#"):
            try:
                pos_str = response[3:-1]  # Убираем $O, и #
                pos = float(pos_str)
                return pos if 0.00 <= pos <= 359.99 else None
            except ValueError:
                pass
        return None
    
    def get_current_tilt_speed(self) -> Optional[float]:
        """
        Получить текущую скорость оси наклона
        Команда: $P#
        Ответ: $P,curSpeed# где curSpeed - скорость в °/c
        Положительное значение - по часовой стрелке, отрицательное - против
        """
        response = self._send_command("$P#")
        if response and response.startswith("$P,") and response.endswith("#"):
            try:
                speed_str = response[3:-1]  # Убираем $P, и #
                speed = float(speed_str)
                return speed
            except ValueError:
                pass
        return None
    
    def get_tilt_busy_status(self) -> Optional[int]:
        """
        Получить статус занятости оси наклона
        Команда: $Q#
        Ответ: $Q,busyStatus# где busyStatus: 0-Удержание, 1-Разгон, 2-Торможение, 3-Равномерное движение
        """
        response = self._send_command("$Q#")
        if response and response.startswith("$Q,") and response.endswith("#"):
            try:
                status_str = response[3:-1]  # Убираем $Q, и #
                status = int(status_str)
                return status
            except ValueError:
                pass
        return None
    
    def get_last_tilt_task(self) -> Optional[int]:
        """
        Получить последнюю принятую к исполнению команду оси наклона
        Команда: $S#
        Ответ: $S,lastTask# где lastTask: 0-Нет команд, 1-Самодиагностика, 2-Стоп, 4-Скорость, 5-Позиция
        """
        response = self._send_command("$S#")
        if response and response.startswith("$S,") and response.endswith("#"):
            try:
                task_str = response[3:-1]  # Убираем $S, и #
                task = int(task_str)
                return task
            except ValueError:
                pass
        return None
    
    def stop_tilt_axis(self) -> bool:
        """
        Стоп для оси наклона
        Команда: $U#
        """
        response = self._send_command("$U#")
        return response is not None
    
    def get_target_tilt_speed(self) -> Optional[float]:
        """
        Получить целевую скорость оси наклона
        Команда: $W#
        Ответ: $W,targetSpeed# где targetSpeed - целевая скорость в °/c
        """
        response = self._send_command("$W#")
        if response and response.startswith("$W,") and response.endswith("#"):
            try:
                speed_str = response[3:-1]  # Убираем $W, и #
                speed = float(speed_str)
                return speed
            except ValueError:
                pass
        return None
    
    def set_tilt_speed(self, speed: float) -> bool:
        """
        Задать скорость оси наклона (начать движение)
        Команда: $W,targetSpeed#
        """
        command = f"$W,{speed:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_target_tilt_position_and_max_speed(self) -> Optional[Tuple[float, float]]:
        """
        Получить целевую позицию и предельную скорость перехода оси наклона
        Команда: $X#
        Ответ: $X,targetPos,maxSpeed#
        где targetPos - целевая позиция в ° от 0.00 до 359.99
        maxSpeed - предельная скорость при переходе в °/с (всегда положительное)
        """
        response = self._send_command("$X#")
        if response and response.startswith("$X,") and response.endswith("#"):
            try:
                # Убираем $X и #, разбиваем по запятым
                values_str = response[3:-1]
                values = values_str.split(',')
                
                if len(values) == 2:
                    target_pos = float(values[0])
                    max_speed = float(values[1])
                    
                    if 0.00 <= target_pos <= 359.99 and max_speed >= 0:
                        return target_pos, max_speed
            except ValueError:
                pass
        return None
    
    def move_to_tilt_position(self, target_pos: float, max_speed: float) -> bool:
        """
        Переход в позицию с заданной скоростью для оси наклона
        Команда: $X,targetPos,maxSpeed#
        """
        if not (0.00 <= target_pos <= 359.99):
            self.logger.error("Target position must be between 0.00 and 359.99 degrees")
            return False
        if max_speed < 0:
            self.logger.error("Max speed must be positive")
            return False
        
        command = f"$X,{target_pos:.2f},{max_speed:.2f}#"
        response = self._send_command(command)
        return response is not None
    
    def get_supply_voltage(self) -> Optional[float]:
        """
        Получить входное напряжение питания (версия ≥1.51)
        Команда: $0#
        Ответ: $0,voltage# где voltage - напряжение питания в вольтах
        """
        response = self._send_command("$0#")
        if response and response.startswith("$0,") and response.endswith("#"):
            try:
                voltage_str = response[3:-1]  # Убираем $0, и #
                voltage = float(voltage_str)
                return voltage
            except ValueError:
                pass
        return None
    
    def close(self):
        """
        Закрытие соединения
        """
        self.disconnect()