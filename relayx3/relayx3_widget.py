import sys
import socket
import struct
import threading
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGroupBox, QSpinBox, QCheckBox, QGridLayout, QTextEdit, QProgressBar,
    QFormLayout, QComboBox, QDoubleSpinBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
import json

# Исправленный импорт конфигурационного менеджера
from camera.config_manager import config_manager


class RelayX3Widget(QWidget):
    """
    Виджет управления устройством RelayX3
    """
    # Сигналы для обновления UI из других потоков
    update_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        
        # Загружаем конфигурацию
        config = config_manager.get_relayx3_config()
        
        # Параметры подключения
        self.tcp_ip = config.get("tcp_ip", "192.168.127.254")  # Изменен IP-адрес
        self.tcp_port = config.get("tcp_port", 9762)  # Изменен порт на 9762
        self.device_address = config.get("device_address", 1)  # Адрес устройства
        self.baud_rate = config.get("baud_rate", 115200)  # Скорость UART
        self.uart_speed_setting = config.get("uart_speed_setting", "11")  # Настройка скорости UART
        self.socket = None
        self.connected = False
        self.connection_thread = None
        self.reconnect_timer = QTimer()
        self.reconnect_timer.setInterval(5000)  # Интервал переподключения 5 секунд
        self.reconnect_timer.timeout.connect(self.connect_to_device)
        
        # Состояния каналов
        self.channel_states = config.get("channel_states", [False, False, False])  # Состояния каналов 1, 2, 3
        
        # Статусы ошибок
        self.error_status = {
            "voltage_check": False,
            "voltage_error": False,
            "polarity_check": False,
            "polarity_error": False,
            "ch1_error": False,
            "ch1_temp_error": False,
            "ch2_error": False,
            "ch2_temp_error": False,
            "ch3_error": False,
            "ch3_temp_error": False
        }
        self.temperature_values = [0.0, 0.0, 0.0]  # Температуры каналов
        self.voltage_values = [0.0]  # Напряжение на входе 1
        self.status_values = [0, 0]  # Статусы
        
        # Таймеры для каналов
        self.timers = {
            "left": {"running": False, "thread": None},
            "right": {"running": False, "thread": None},
            "third": {"running": False, "thread": None}
        }
        
        # Применить тему оформления
        self.apply_theme()
        
        self.setup_ui()
        self.setup_signals()
        
    def apply_theme(self):
        """Применить тему оформления"""
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            
            QGroupBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 6px;
                margin-top: 1ex;
                padding: 10px;
                font-weight: bold;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0px 5px 0px 5px;
                color: #ffffff;
            }
            
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 80px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
            
            QPushButton:pressed {
                background-color: #3a3a3a;
                border: 1px solid #555555;
            }
            
            QPushButton:disabled {
                background-color: #333333;
                color: #777777;
                border: 1px solid #444444;
            }
            
            QCheckBox {
                spacing: 5px;
            }
            
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            
            QCheckBox::indicator:unchecked {
                border: 2px solid #777777;
                background-color: #3c3c3c;
            }
            
            QCheckBox::indicator:checked {
                border: 2px solid #777777;
                background-color: #5a5a5a;
            }
            
            QSpinBox, QDoubleSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #777777;
            }
            
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QLineEdit:focus {
                border: 1px solid #777777;
            }
            
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QProgressBar {
                border: 1px solid #555555;
                background-color: #3c3c3c;
                text-align: center;
            }
            
            QProgressBar::chunk {
                background-color: #5a5a5a;
            }
        """)
    
    def setup_signals(self):
        """Настроить сигналы для обновления UI"""
        self.update_signal.connect(self.update_display)
        self.status_signal.connect(self.update_status)
        self.error_signal.connect(self.handle_error)
    
    def setup_ui(self):
        """Настроить пользовательский интерфейс"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Заголовок
        title_label = QLabel("Устройство управления реле RelayX3")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Группа подключения
        connection_group = QGroupBox("Параметры подключения")
        connection_layout = QFormLayout()
        
        # IP-адрес
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.tcp_ip)
        self.ip_input.textChanged.connect(self.change_ip_address)
        connection_layout.addRow("IP-адрес:", self.ip_input)
        
        # Порт
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1, 65535)
        self.port_spinbox.setValue(self.tcp_port)
        self.port_spinbox.valueChanged.connect(self.change_port)
        connection_layout.addRow("Порт:", self.port_spinbox)
        
        # Адрес устройства
        self.address_spinbox = QSpinBox()
        self.address_spinbox.setRange(0, 255)
        self.address_spinbox.setValue(self.device_address)
        self.address_spinbox.valueChanged.connect(self.change_device_address)
        connection_layout.addRow("Адрес устройства:", self.address_spinbox)
        
        # Скорость UART (в соответствии с 2-битным переключателем)
        self.uart_speed_combo = QComboBox()
        self.uart_speed_combo.addItems(["9600 (00)", "19200 (01)", "38400 (10)", "115200 (11)"])
        # Установить текущий выбор в зависимости от сохраненного значения
        if self.uart_speed_setting == "00":
            self.uart_speed_combo.setCurrentIndex(0)
        elif self.uart_speed_setting == "01":
            self.uart_speed_combo.setCurrentIndex(1)
        elif self.uart_speed_setting == "10":
            self.uart_speed_combo.setCurrentIndex(2)
        else:  # "11" или по умолчанию
            self.uart_speed_combo.setCurrentIndex(3)
        self.uart_speed_combo.currentTextChanged.connect(self.change_uart_speed)
        connection_layout.addRow("Скорость UART:", self.uart_speed_combo)
        
        # Кнопки подключения
        connection_buttons_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("Подключиться")
        self.connect_button.clicked.connect(self.connect_to_device)
        
        self.disconnect_button = QPushButton("Отключиться")
        self.disconnect_button.clicked.connect(self.disconnect_from_device)
        self.disconnect_button.setEnabled(False)
        
        connection_buttons_layout.addWidget(self.connect_button)
        connection_buttons_layout.addWidget(self.disconnect_button)
        connection_buttons_layout.addStretch()
        
        connection_layout.addRow(connection_buttons_layout)
        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)
        
        # Группа управления каналами
        channels_group = QGroupBox("Управление каналами")
        channels_layout = QGridLayout()
        
        # Канал 1
        self.channel1_checkbox = QCheckBox("Канал 1")
        self.channel1_checkbox.stateChanged.connect(lambda state: self.toggle_channel(1, state))
        
        self.channel1_status_label = QLabel("Выключен")
        self.channel1_status_label.setStyleSheet("color: red;")
        
        channels_layout.addWidget(self.channel1_checkbox, 0, 0)
        channels_layout.addWidget(self.channel1_status_label, 0, 1)
        
        # Канал 2
        self.channel2_checkbox = QCheckBox("Канал 2")
        self.channel2_checkbox.stateChanged.connect(lambda state: self.toggle_channel(2, state))
        
        self.channel2_status_label = QLabel("Выключен")
        self.channel2_status_label.setStyleSheet("color: red;")
        
        channels_layout.addWidget(self.channel2_checkbox, 1, 0)
        channels_layout.addWidget(self.channel2_status_label, 1, 1)
        
        # Канал 3
        self.channel3_checkbox = QCheckBox("Канал 3")
        self.channel3_checkbox.stateChanged.connect(lambda state: self.toggle_channel(3, state))
        
        self.channel3_status_label = QLabel("Выключен")
        self.channel3_status_label.setStyleSheet("color: red;")
        
        channels_layout.addWidget(self.channel3_checkbox, 2, 0)
        channels_layout.addWidget(self.channel3_status_label, 2, 1)
        
        # Кнопки для управления всеми каналами
        all_channels_layout = QHBoxLayout()
        
        self.all_on_button = QPushButton("Включить все")
        self.all_on_button.clicked.connect(self.turn_all_on)
        self.all_on_button.setEnabled(False)
        
        self.all_off_button = QPushButton("Выключить все")
        self.all_off_button.clicked.connect(self.turn_all_off)
        self.all_off_button.setEnabled(False)
        
        all_channels_layout.addWidget(self.all_on_button)
        all_channels_layout.addWidget(self.all_off_button)
        all_channels_layout.addStretch()
        
        channels_layout.addLayout(all_channels_layout, 3, 0, 1, 2)
        channels_group.setLayout(channels_layout)
        layout.addWidget(channels_group)
        
        # Группа мониторинга
        monitoring_group = QGroupBox("Мониторинг состояния")
        monitoring_layout = QVBoxLayout()
        
        # Состояние подключения
        self.connection_status_label = QLabel("Статус подключения: Не подключено")
        monitoring_layout.addWidget(self.connection_status_label)
        
        # Температура
        self.temp_label = QLabel("Температура: -- °C")
        monitoring_layout.addWidget(self.temp_label)
        
        # Напряжение
        self.voltage_label = QLabel("Напряжение: -- В")
        monitoring_layout.addWidget(self.voltage_label)
        
        # Статус
        self.status_label = QLabel("Статус: --")
        monitoring_layout.addWidget(self.status_label)
        
        # Кнопки запроса информации
        info_buttons_layout = QHBoxLayout()
        
        self.request_temp_button = QPushButton("Запросить температуру")
        self.request_temp_button.clicked.connect(self.request_temperature)
        self.request_temp_button.setEnabled(False)
        
        self.request_voltage_button = QPushButton("Запросить напряжение")
        self.request_voltage_button.clicked.connect(self.request_voltage)
        self.request_voltage_button.setEnabled(False)
        
        self.request_status_button = QPushButton("Запросить статус")
        self.request_status_button.clicked.connect(self.request_status)
        self.request_status_button.setEnabled(False)
        
        info_buttons_layout.addWidget(self.request_temp_button)
        info_buttons_layout.addWidget(self.request_voltage_button)
        info_buttons_layout.addWidget(self.request_status_button)
        info_buttons_layout.addStretch()
        
        monitoring_layout.addLayout(info_buttons_layout)
        monitoring_group.setLayout(monitoring_layout)
        layout.addWidget(monitoring_group)
        
        # Лог действий
        log_group = QGroupBox("Лог событий")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Растянуть последний элемент
        layout.addStretch()
        
        self.setLayout(layout)
        
        # Установить начальное состояние чекбоксов
        self.update_channel_display()
    
    def connect_to_device(self):
        """Подключиться к устройству"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)  # Таймаут 5 секунд
            self.socket.connect((self.tcp_ip, self.tcp_port))
            self.connected = True
            
            self.log_message(f"Подключено к {self.tcp_ip}:{self.tcp_port}")
            self.update_connection_status()
            
            # Запустить поток для получения данных
            self.connection_thread = threading.Thread(target=self.receive_data)
            self.connection_thread.daemon = True
            self.connection_thread.start()
            
        except Exception as e:
            self.log_message(f"Ошибка подключения: {str(e)}")
            self.connected = False
            self.update_connection_status()
    
    def disconnect_from_device(self):
        """Отключиться от устройства"""
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.log_message("Отключено от устройства")
        self.update_connection_status()
    
    def update_connection_status(self):
        """Обновить статус подключения"""
        if self.connected:
            self.connection_status_label.setText(f"Статус подключения: Подключено к {self.tcp_ip}:{self.tcp_port}")
            self.connection_status_label.setStyleSheet("color: green;")
            
            # Включить кнопки управления
            self.disconnect_button.setEnabled(True)
            self.connect_button.setEnabled(False)
            self.all_on_button.setEnabled(True)
            self.all_off_button.setEnabled(True)
            self.request_temp_button.setEnabled(True)
            self.request_voltage_button.setEnabled(True)
            self.request_status_button.setEnabled(True)
            
            # Включить чекбоксы каналов
            self.channel1_checkbox.setEnabled(True)
            self.channel2_checkbox.setEnabled(True)
            self.channel3_checkbox.setEnabled(True)
            
            # Остановить таймер автоматического переподключения
            self.reconnect_timer.stop()
        else:
            self.connection_status_label.setText("Статус подключения: Не подключено")
            self.connection_status_label.setStyleSheet("color: red;")
            
            # Отключить кнопки управления
            self.disconnect_button.setEnabled(False)
            self.connect_button.setEnabled(True)
            self.all_on_button.setEnabled(False)
            self.all_off_button.setEnabled(False)
            self.request_temp_button.setEnabled(False)
            self.request_voltage_button.setEnabled(False)
            self.request_status_button.setEnabled(False)
            
            # Отключить чекбоксы каналов
            self.channel1_checkbox.setEnabled(False)
            self.channel2_checkbox.setEnabled(False)
            self.channel3_checkbox.setEnabled(False)
            
            # Включить таймер автоматического переподключения
            if not self.reconnect_timer.isActive():
                self.reconnect_timer.start()
    
    def change_ip_address(self, ip):
        """Изменить IP-адрес"""
        self.tcp_ip = ip
        self.log_message(f"IP-адрес изменен на {ip}")
        
        # Обновить конфигурацию
        main_config = config_manager.config
        if "relayx3" not in main_config:
            main_config["relayx3"] = {}
        main_config["relayx3"]["tcp_ip"] = ip
        config_manager.save_config(main_config)
    
    def change_port(self, port):
        """Изменить порт"""
        self.tcp_port = port
        self.log_message(f"Порт изменен на {port}")
        
        # Обновить конфигурацию
        main_config = config_manager.config
        if "relayx3" not in main_config:
            main_config["relayx3"] = {}
        main_config["relayx3"]["tcp_port"] = port
        config_manager.save_config(main_config)
    
    def change_device_address(self, address):
        """Изменить адрес устройства"""
        self.device_address = address
        self.log_message(f"Адрес устройства изменен на {address}")
        
        # Обновить конфигурацию
        main_config = config_manager.config
        if "relayx3" not in main_config:
            main_config["relayx3"] = {}
        main_config["relayx3"]["device_address"] = address
        config_manager.save_config(main_config)
    
    def change_uart_speed(self, speed_text):
        """Изменить скорость UART"""
        # Извлечь числовое значение из текста (например, "115200 (11)" -> "11")
        speed_code = speed_text.split('(')[-1].replace(')', '')
        self.uart_speed_setting = speed_code
        
        # Определить фактическую скорость в бодах
        if speed_code == "00":
            self.baud_rate = 9600
        elif speed_code == "01":
            self.baud_rate = 19200
        elif speed_code == "10":
            self.baud_rate = 38400
        else:  # "11"
            self.baud_rate = 115200
            
        self.log_message(f"Скорость UART изменена на {self.baud_rate} бод ({speed_code})")
        
        # Обновить конфигурацию
        main_config = config_manager.config
        if "relayx3" not in main_config:
            main_config["relayx3"] = {}
        main_config["relayx3"]["uart_speed_setting"] = speed_code
        main_config["relayx3"]["baud_rate"] = self.baud_rate
        config_manager.save_config(main_config)
    
    def toggle_channel(self, channel, state):
        """Включить/выключить канал"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        try:
            # Для протокола Pelco-D формируем команды в формате:
            # FF AA BB CC DD EE SS где:
            # FF - стартовый байт
            # AA - адрес устройства
            # BB - команда (88 вкл, 08 выкл для канала 1)
            # CC - дополнительные параметры (в данном случае 00)
            # DD - EE - зарезервированы (00 00)
            # SS - контрольная сумма
            
            if channel == 1:
                if state == Qt.CheckState.Checked.value:
                    # Команда включения канала 1: FF 01 88 00 00 00 89
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x88, 0x00, 0x00, 0x00, 0x89)
                else:
                    # Команда выключения канала 1: FF 01 08 00 00 00 09
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x08, 0x00, 0x00, 0x00, 0x09)
            elif channel == 2:
                if state == Qt.CheckState.Checked.value:
                    # Команда включения канала 2: FF 01 02 00 00 00 03
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x02, 0x00, 0x00, 0x00, 0x03)
                else:
                    # Команда выключения канала 2: FF 01 04 00 00 00 05
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x04, 0x00, 0x00, 0x00, 0x05)
            elif channel == 3:
                if state == Qt.CheckState.Checked.value:
                    # Команда включения канала 3: FF 01 00 20 00 00 21
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x20, 0x00, 0x00, 0x21)
                else:
                    # Команда выключения канала 3: FF 01 00 40 00 00 41
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x40, 0x00, 0x00, 0x41)
            else:
                return
            
            # Отправить команду
            self.socket.send(packet)
            
            # Обновить состояние
            self.channel_states[channel-1] = (state == Qt.CheckState.Checked.value)
            self.update_channel_display()
            
            # Обновить конфигурацию
            main_config = config_manager.config
            if "relayx3" not in main_config:
                main_config["relayx3"] = {}
            main_config["relayx3"]["channel_states"] = self.channel_states
            config_manager.save_config(main_config)
            
            self.log_message(f"Канал {channel} {'включен' if state == Qt.CheckState.Checked.value else 'выключен'}")
            
        except Exception as e:
            self.log_message(f"Ошибка управления каналом {channel}: {str(e)}")
    
    def turn_all_on(self):
        """Включить все каналы"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        try:
            # Включить все каналы по очереди
            for channel in [1, 2, 3]:
                if channel == 1:
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x88, 0x00, 0x00, 0x00, 0x89)
                elif channel == 2:
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x02, 0x00, 0x00, 0x00, 0x03)
                else:  # channel == 3
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x20, 0x00, 0x00, 0x21)
                
                self.socket.send(packet)
                time.sleep(0.1)  # Небольшая задержка между командами
            
            # Обновить состояние
            self.channel_states = [True, True, True]
            self.update_channel_display()
            
            # Обновить конфигурацию
            main_config = config_manager.config
            if "relayx3" not in main_config:
                main_config["relayx3"] = {}
            main_config["relayx3"]["channel_states"] = self.channel_states
            config_manager.save_config(main_config)
            
            self.log_message("Все каналы включены")
            
        except Exception as e:
            self.log_message(f"Ошибка включения всех каналов: {str(e)}")
    
    def turn_all_off(self):
        """Выключить все каналы"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        try:
            # Выключить все каналы по очереди
            for channel in [1, 2, 3]:
                if channel == 1:
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x08, 0x00, 0x00, 0x00, 0x09)
                elif channel == 2:
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x04, 0x00, 0x00, 0x00, 0x05)
                else:  # channel == 3
                    packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x40, 0x00, 0x00, 0x41)
                
                self.socket.send(packet)
                time.sleep(0.1)  # Небольшая задержка между командами
            
            # Обновить состояние
            self.channel_states = [False, False, False]
            self.update_channel_display()
            
            # Обновить конфигурацию
            main_config = config_manager.config
            if "relayx3" not in main_config:
                main_config["relayx3"] = {}
            main_config["relayx3"]["channel_states"] = self.channel_states
            config_manager.save_config(main_config)
            
            self.log_message("Все каналы выключены")
            
        except Exception as e:
            self.log_message(f"Ошибка выключения всех каналов: {str(e)}")
    
    def send_command(self, command):
        """Отправить команду на устройство"""
        if not self.socket or not self.connected:
            return False
        
        try:
            # Для совместимости с остальными частями кода - отправка команды в формате Pelco-D
            # если это специфичная команда, а не простая установка канала
            if command in [0x0071, 0x0073, 0x0077]:  # Команды запроса данных
                addr = self.device_address
                high_byte = (command >> 8) & 0xFF
                low_byte = command & 0xFF
                
                # Расчет контрольной суммы (по спецификации Pelco-D: сумма по модулю 256)
                checksum = (0xFF + addr + high_byte + low_byte) & 0xFF
                
                packet = struct.pack('BBBBB', 0xFF, addr, high_byte, low_byte, checksum)
                
                self.socket.send(packet)
                return True
            else:
                # Для команд включения/выключения каналов используем специфичные команды
                self.log_message(f"Команда {command} не поддерживается напрямую, используйте toggle_channel")
                return False
            
        except Exception as e:
            self.log_message(f"Ошибка отправки команды: {str(e)}")
            return False
    
    def request_temperature(self):
        """Запросить температуру"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        try:
            # Команда 0x0071 - read temperature
            packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x71, 0x00, 0x00, 0x72)
            self.socket.send(packet)
            self.log_message("Отправлен запрос температуры")
            
        except Exception as e:
            self.log_message(f"Ошибка запроса температуры: {str(e)}")
    
    def request_voltage(self):
        """Запросить напряжение"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        try:
            # Команда 0x0073 - read voltage
            packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x73, 0x00, 0x00, 0x74)
            self.socket.send(packet)
            self.log_message("Отправлен запрос напряжения")
            
        except Exception as e:
            self.log_message(f"Ошибка запроса напряжения: {str(e)}")
    
    def request_status(self):
        """Запросить статус"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        try:
            # Команда 0x0077 - read status
            packet = struct.pack('BBBBBBB', 0xFF, self.device_address, 0x00, 0x77, 0x00, 0x00, 0x78)
            self.socket.send(packet)
            self.log_message("Отправлен запрос статуса")
            
        except Exception as e:
            self.log_message(f"Ошибка запроса статуса: {str(e)}")
    
    def receive_data(self):
        """Получать данные из сокета в отдельном потоке"""
        while self.connected:
            try:
                if self.socket:
                    data = self.socket.recv(1024)
                    if data:
                        self.process_received_data(data)
            except socket.timeout:
                continue
            except Exception as e:
                if self.connected:  # Только если соединение было активно
                    self.log_message(f"Ошибка получения данных: {str(e)}")
                break
            time.sleep(0.1)  # Небольшая задержка для снижения нагрузки на CPU
    
    def process_received_data(self, data):
        """Обработать полученные данные"""
        try:
            # Обработка ответа по протоколу Pelco-D
            if len(data) >= 7 and data[0] == 0xFF:
                addr = data[1]
                cmd = (data[2] << 8) | data[3]
                msb = data[4]
                lsb = data[5]
                checksum = data[6]
                
                # Проверяем контрольную сумму
                calculated_checksum = (0xFF + addr + data[2] + data[3] + msb + lsb) & 0xFF
                if checksum != calculated_checksum:
                    self.log_message("Неверная контрольная сумма в ответе")
                    return
                
                # Обработка разных типов ответов
                if cmd == 0x0071:  # Ответ на запрос температуры
                    # Температура в формате signed short, умноженная на 100
                    temp_raw = struct.unpack('>h', bytes([msb, lsb]))[0]
                    temperature = temp_raw / 100.0
                    self.temperature_values[0] = temperature
                    self.temp_label.setText(f"Температура: {temperature:.2f} °C")
                    self.update_signal.emit(f"Получена температура: {temperature:.2f} °C")
                
                elif cmd == 0x0073:  # Ответ на запрос напряжения
                    # Напряжение в формате unsigned short, умноженное на 100
                    voltage_raw = struct.unpack('>H', bytes([msb, lsb]))[0]
                    voltage = voltage_raw / 100.0
                    self.voltage_values[0] = voltage
                    self.voltage_label.setText(f"Напряжение: {voltage:.2f} В")
                    self.update_signal.emit(f"Получено напряжение: {voltage:.2f} В")
                
                elif cmd == 0x0077:  # Ответ на запрос статуса
                    status_raw = (msb << 8) | lsb
                    
                    # Разбор битовой маски статуса
                    self.error_status["voltage_check"] = bool(status_raw & 0x0001)
                    self.error_status["voltage_error"] = bool(status_raw & 0x0002)
                    self.error_status["polarity_check"] = bool(status_raw & 0x0004)
                    self.error_status["polarity_error"] = bool(status_raw & 0x0008)
                    ch1_on = bool(status_raw & 0x0010)
                    self.error_status["ch1_error"] = bool(status_raw & 0x0020)
                    self.error_status["ch1_temp_error"] = bool(status_raw & 0x0040)
                    ch2_on = bool(status_raw & 0x0080)
                    self.error_status["ch2_error"] = bool(status_raw & 0x0100)
                    self.error_status["ch2_temp_error"] = bool(status_raw & 0x0200)
                    ch3_on = bool(status_raw & 0x0400)
                    self.error_status["ch3_error"] = bool(status_raw & 0x0800)
                    self.error_status["ch3_temp_error"] = bool(status_raw & 0x1000)
                    
                    # Обновить отображение статуса
                    self.update_status_display()
                    
                    # Обновить отображение чекбоксов в соответствии с реальным состоянием
                    self.update_channel_display_from_status(ch1_on, ch2_on, ch3_on)
            
            # Другие типы данных обрабатываются по необходимости
        except Exception as e:
            self.log_message(f"Ошибка обработки полученных данных: {str(e)}")
    
    def update_channel_display_from_status(self, ch1_on, ch2_on, ch3_on):
        """Обновить отображение чекбоксов в соответствии с реальным статусом"""
        # Блокируем сигналы, чтобы не вызвать рекурсивное изменение состояния
        self.channel1_checkbox.blockSignals(True)
        self.channel2_checkbox.blockSignals(True)
        self.channel3_checkbox.blockSignals(True)
        
        self.channel1_checkbox.setChecked(ch1_on)
        self.channel2_checkbox.setChecked(ch2_on)
        self.channel3_checkbox.setChecked(ch3_on)
        
        # Восстанавливаем сигналы
        self.channel1_checkbox.blockSignals(False)
        self.channel2_checkbox.blockSignals(False)
        self.channel3_checkbox.blockSignals(False)
        
        # Обновляем состояние
        self.channel_states[0] = ch1_on
        self.channel_states[1] = ch2_on
        self.channel_states[2] = ch3_on
        self.update_channel_display()
    
    def update_channel_display(self):
        """Обновить отображение состояния каналов"""
        for i, state in enumerate(self.channel_states):
            label = getattr(self, f'channel{i+1}_status_label')
            label.setText("Включен" if state else "Выключен")
            
            # Учет ошибок при визуализации каналов
            if self.error_status[f"ch{i+1}_error"]:
                label.setStyleSheet("color: orange;")
            elif self.error_status[f"ch{i+1}_temp_error"]:
                label.setStyleSheet("color: red;")
            else:
                label.setStyleSheet("color: green;" if state else "color: red;")
    
    def update_status_display(self):
        """Обновить отображение статуса с визуализацией ошибок"""
        status_text = "Статус: "
        
        # Статус канала 1
        ch1_status = "OK" if not (self.error_status["ch1_error"] or self.error_status["ch1_temp_error"]) else \
                    "ERR" if self.error_status["ch1_error"] else "TEMP"
        ch1_color = "green" if ch1_status == "OK" else "orange" if ch1_status == "ERR" else "red"
        
        # Статус канала 2
        ch2_status = "OK" if not (self.error_status["ch2_error"] or self.error_status["ch2_temp_error"]) else \
                    "ERR" if self.error_status["ch2_error"] else "TEMP"
        ch2_color = "green" if ch2_status == "OK" else "orange" if ch2_status == "ERR" else "red"
        
        # Статус канала 3
        ch3_status = "OK" if not (self.error_status["ch3_error"] or self.error_status["ch3_temp_error"]) else \
                    "ERR" if self.error_status["ch3_error"] else "TEMP"
        ch3_color = "green" if ch3_status == "OK" else "orange" if ch3_status == "ERR" else "red"
        
        status_text += f'Ch1:<font color="{ch1_color}">{ch1_status}</font>, ' \
                      f'Ch2:<font color="{ch2_color}">{ch2_status}</font>, ' \
                      f'Ch3:<font color="{ch3_color}">{ch3_status}</font>'
        
        self.status_label.setText(status_text)
        
        # Дополнительная информация об ошибках
        error_details = []
        if self.error_status["voltage_error"]:
            error_details.append("Низкое напряжение питания")
        if self.error_status["polarity_error"]:
            error_details.append("Ошибка полярности питания")
            
        if error_details:
            self.update_signal.emit(f"Получен статус с ошибками: {', '.join(error_details)}")
        else:
            self.update_signal.emit("Получен статус: Все системы в норме")
    
    def update_display(self, message):
        """Обновить дисплей (обработка сигнала)"""
        self.log_message(message)
    
    def update_status(self, message):
        """Обновить статус (обработка сигнала)"""
        self.connection_status_label.setText(message)
    
    def handle_error(self, message):
        """Обработка ошибки (обработка сигнала)"""
        self.log_message(f"ОШИБКА: {message}")
    
    def log_message(self, message):
        """Добавить сообщение в лог"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        current_text = self.log_text.toPlainText()
        self.log_text.setPlainText(current_text + "\n" + formatted_message)
        # Прокрутить вниз
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        # Очистить все таймеры
        if self.reconnect_timer:
            self.reconnect_timer.stop()
        event.accept()
    
    def start_timer(self, channel):
        """Запустить таймер для канала"""
        if not self.connected:
            self.log_message("Сначала подключитесь к устройству")
            return
        
        # Проверить, запущен ли уже таймер для этого канала
        if self.timers[channel]["running"]:
            self.log_message(f"Таймер для канала {channel} уже запущен")
            return
        
        # Получить время из соответствующего спинбокса
        if channel == "left":
            duration = self.channel1_time_spinbox.value()
        elif channel == "right":
            duration = self.channel2_time_spinbox.value()
        else:  # third
            duration = self.channel3_time_spinbox.value()
        
        # Отметить таймер как запущенный
        self.timers[channel]["running"] = True
        
        # Создать новый поток для таймера
        timer_thread = threading.Thread(target=self.run_timer, args=(channel, duration))
        timer_thread.daemon = True
        timer_thread.start()
        self.timers[channel]["thread"] = timer_thread
        
        self.log_message(f"Запущен таймер для канала {channel} на {duration} секунд")
    
    def stop_timer(self, channel):
        """Остановить таймер для канала"""
        self.timers[channel]["running"] = False
        self.log_message(f"Таймер для канала {channel} остановлен")
        
        # Выключить канал
        if channel == "left":
            self.toggle_channel(1, Qt.CheckState.Unchecked.value)
        elif channel == "right":
            self.toggle_channel(2, Qt.CheckState.Unchecked.value)
        else:  # third
            self.toggle_channel(3, Qt.CheckState.Unchecked.value)
    
    def run_timer(self, channel, duration):
        """Выполнить таймер в отдельном потоке"""
        # Включить канал
        if channel == "left":
            self.toggle_channel(1, Qt.CheckState.Checked.value)
        elif channel == "right":
            self.toggle_channel(2, Qt.CheckState.Checked.value)
        else:  # third
            self.toggle_channel(3, Qt.CheckState.Checked.value)
        
        # Ждать указанное время или пока таймер не будет остановлен
        start_time = time.time()
        while time.time() - start_time < duration and self.timers[channel]["running"]:
            time.sleep(0.1)
        
        # Если таймер все еще должен работать, выключить канал
        if self.timers[channel]["running"]:
            if channel == "left":
                self.toggle_channel(1, Qt.CheckState.Unchecked.value)
            elif channel == "right":
                self.toggle_channel(2, Qt.CheckState.Unchecked.value)
            else:  # third
                self.toggle_channel(3, Qt.CheckState.Unchecked.value)
        
        # Отметить таймер как остановленный
        self.timers[channel]["running"] = False
