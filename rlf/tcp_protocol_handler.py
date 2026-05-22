"""
TCP Protocol handler for the 3km eye-safe laser rangefinder module
Implements the communication protocol over TCP/IP
"""

import struct
import time
import socket


class TcpProtocolHandler:
    """Handles communication with the laser rangefinder module over TCP/IP"""
    
    # Command codes
    CMD_SELF_CHECK = 0x01
    CMD_SINGLE_RANGING = 0x02
    CMD_SET_TARGET_MODE = 0x03
    CMD_CONTINUE_RANGING = 0x04
    CMD_STOP_RANGING = 0x05
    CMD_RANGING_ABNORMAL = 0x06
    CMD_LOW_POWER_WAKEUP = 0x07
    
    # Configuration commands
    CMD_SET_BAUD_RATE = 0xA0
    CMD_SET_FREQUENCY = 0xA1
    CMD_SET_MIN_DISTANCE = 0xA2
    CMD_QUERY_MIN_DISTANCE = 0xA3
    CMD_SET_MAX_DISTANCE = 0xA4
    CMD_QUERY_MAX_DISTANCE = 0xA5
    CMD_QUERY_FPGA_VERSION = 0xA6
    CMD_QUERY_MCU_VERSION = 0xA7
    CMD_QUERY_HARDWARE_VERSION = 0xA8
    CMD_QUERY_SN_NUMBER = 0xA9
    CMD_QUERY_TOTAL_LIGHT_OUTPUT = 0x90
    CMD_QUERY_POWER_ON_LIGHT_OUTPUT = 0x91
    
    # Target modes
    TARGET_FIRST = 0x01
    TARGET_LAST = 0x02
    TARGET_MULTI = 0x03
    
    def __init__(self, tcp_socket):
        """
        Initialize the TCP protocol handler with a socket object
        :param tcp_socket: socket.socket object
        """
        self.tcp_socket = tcp_socket

    def _calculate_checksum(self, data):
        """
        Calculate checksum as sum of data bytes modulo 256
        :param data: List of bytes
        :return: Checksum byte
        """
        return sum(data) & 0xFF

    def _build_packet(self, command_code, params=None):
        """
        Build a communication packet according to the protocol
        :param command_code: Command code byte
        :param params: List of parameter bytes (optional)
        :return: Complete packet as list of bytes
        """
        if params is None:
            params = []
        
        # Calculate data length (device code + command code + params)
        data_length = 1 + 1 + len(params)
        
        # Build packet: Frame head + Data length + Device code + Command code + Params + Checksum
        packet = [0xEE, 0x16, data_length, 0x03, command_code]  # Frame head, data length, device code
        packet.extend(params)
        
        # Calculate and append checksum
        checksum_data = packet[3:]  # From device code onwards
        checksum = self._calculate_checksum(checksum_data)
        packet.append(checksum)
        
        return packet

    def send_command(self, command_code, params=None):
        """
        Send a command to the rangefinder module over TCP
        :param command_code: Command code byte
        :param params: List of parameter bytes (optional)
        :return: True if sent successfully, False otherwise
        """
        try:
            packet = self._build_packet(command_code, params)
            self.tcp_socket.send(bytes(packet))
            return True
        except Exception as e:
            print(f"Error sending command {command_code:02X} over TCP: {str(e)}")
            return False

    def read_response(self, timeout=2.0):
        """
        Read a response packet from the rangefinder module over TCP
        :param timeout: Timeout in seconds
        :return: Response packet as list of bytes, or None if error/timeouts
        """
        self.tcp_socket.settimeout(timeout)
        
        try:
            # Read at least the header (0xEE 0x16) and length byte
            header_and_length = self.tcp_socket.recv(3)
            
            if len(header_and_length) < 3:
                print("Could not read full header from TCP connection")
                return None
            
            # Check if we have the correct header
            if header_and_length[0] != 0xEE or header_and_length[1] != 0x16:
                print(f"Invalid header received: {header_and_length[:2]}")
                return None
            
            # Get the data length
            length_byte = header_and_length[2]
            
            # Now read the rest of the packet (device code + command code + params + checksum)
            remaining_bytes = self.tcp_socket.recv(length_byte + 1)
            
            if len(remaining_bytes) != length_byte + 1:
                print("Could not read full packet from TCP connection")
                return None
            
            # Combine everything into the complete packet
            packet = [0xEE, 0x16, length_byte] + list(remaining_bytes)
            return packet
            
        except socket.timeout:
            print("Timeout waiting for response from TCP connection")
            return None
        except Exception as e:
            print(f"Error reading response from TCP connection: {str(e)}")
            return None

    # Copy the rest of the methods from the ProtocolHandler class
    def _parse_response(self, response):
        """
        Parse a response packet
        :param response: Response packet as list of bytes
        :return: Dictionary with parsed data
        """
        if len(response) < 6:
            return None

        # Extract components
        device_code = response[3]
        command_code = response[4]
        params = response[5:-1]  # All bytes except the last (checksum)
        checksum = response[-1]

        # Verify checksum
        calculated_checksum = self._calculate_checksum(response[3:-1])
        if calculated_checksum != checksum:
            print(f"Checksum mismatch: expected {calculated_checksum:02X}, got {checksum:02X}")
            return None

        return {
            'device_code': device_code,
            'command_code': command_code,
            'params': params,
            'checksum': checksum
        }

    def self_check(self):
        """
        Perform equipment self-check
        :return: Self-check result dictionary or None on failure
        """
        self.send_command(self.CMD_SELF_CHECK)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_SELF_CHECK and len(parsed['params']) == 4:
                # Parse status bytes
                status3, status2, status1, status0 = parsed['params']

                return {
                    'status3': status3,  # Reserved
                    'echo_intensity': status2,
                    'fpga_system_status': bool(status1 & 0x01),
                    'laser_light_output': bool(status1 & 0x02),
                    'main_wave_detection': bool(status1 & 0x04),
                    'echo_detection': bool(status1 & 0x08),
                    'bias_switch': bool(status1 & 0x10),
                    'bias_output': bool(status1 & 0x20),
                    'temperature_state': bool(status1 & 0x40),
                    'light_output_off': bool(status1 & 0x80),
                    'power_5v6_status': bool(status0 & 0x01)
                }

        return None

    def single_ranging(self):
        """
        Perform a single ranging measurement
        :return: Distance measurement result or None on failure
        """
        print("Sending single ranging command...")
        self.send_command(self.CMD_SINGLE_RANGING)
        response = self.read_response()
        
        if response:
            print(f"Received raw response: {' '.join([f'{byte:02X}' for byte in response])}")
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_SINGLE_RANGING and len(parsed['params']) == 4:
                status, dist_high, dist_low, dist_decimal = parsed['params']
                
                print(f"Status: {status:02X}, DistHigh: {dist_high:02X}, DistLow: {dist_low:02X}, Decimal: {dist_decimal:02X}")
                
                # Calculate distance
                distance = dist_high * 256 + dist_low + dist_decimal * 0.1
                
                # Decode status
                status_desc = self._decode_ranging_status(status)
                
                print(f"Calculated distance: {distance}, Status: {status_desc}")
                
                return {
                    'distance': distance,
                    'status': status,
                    'status_description': status_desc
                }
            else:
                print(f"Response parsing failed or wrong command code/length. Parsed: {parsed}")
        else:
            print("No response received from device")
        
        return None

    # Добавим метод для декодирования статуса, аналогичный основному обработчику
    def _decode_ranging_status(self, status):
        """
        Decode the ranging status byte according to the protocol specification
        """
        # For first/last target ranging (when upper 4 bits are 0)
        upper_nibble = (status >> 4) & 0x0F
        lower_nibble = status & 0x0F
        
        if upper_nibble == 0:  # Single target ranging mode
            if lower_nibble == 0x00:
                return "Single target"
            elif lower_nibble == 0x01:
                return "Front target detected"
            elif lower_nibble == 0x02:
                return "Rear target detected"
            elif lower_nibble == 0x03:
                return "Reserved"
            elif lower_nibble == 0x04:
                return "Out of range"
            elif lower_nibble == 0x05:
                return "Reserved"
            else:
                return f"Unknown status (0x{status:02X})"
        else:  # Multi-target ranging mode
            # Upper 4 bits indicate target number
            target_num = upper_nibble
            target_type = lower_nibble
            
            if target_type == 0x0:
                target_desc = "Single target"
            elif target_type == 0x1:
                target_desc = "Front target"
            elif target_type == 0x2:
                target_desc = "Rear target"
            elif target_type == 0x3:
                target_desc = "Front and rear targets"
            elif target_type == 0x4:
                target_desc = "Out of range"
            else:
                target_desc = f"Reserved (0x{target_type:02X})"
            
            return f"Target #{target_num}: {target_desc}"

    def set_target_mode(self, target_mode):
        """
        Set the ranging target mode (first, last, or multi-target)
        :param target_mode: One of TARGET_FIRST, TARGET_LAST, TARGET_MULTI
        :return: True if successful, False otherwise
        """
        if target_mode not in [self.TARGET_FIRST, self.TARGET_LAST, self.TARGET_MULTI]:
            return False

        self.send_command(self.CMD_SET_TARGET_MODE, [target_mode])
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_SET_TARGET_MODE:
                return True

        return False

    def start_continuous_ranging(self):
        """
        Start continuous ranging
        :return: True if successful, False otherwise
        """
        self.send_command(self.CMD_CONTINUE_RANGING)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_CONTINUE_RANGING:
                return True

        return False

    def stop_ranging(self):
        """
        Stop ranging operation
        :return: True if successful, False otherwise
        """
        self.send_command(self.CMD_STOP_RANGING)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_STOP_RANGING:
                return True

        return False

    def set_ranging_frequency(self, frequency):
        """
        Set the ranging frequency (1-10 Hz)
        :param frequency: Frequency in Hz (1-10)
        :return: True if successful, False otherwise
        """
        if not 1 <= frequency <= 10:
            raise ValueError("Frequency must be between 1 and 10 Hz")

        # Frequency value as byte and a reserved byte (0x00)
        params = [frequency, 0x00]
        self.send_command(self.CMD_SET_FREQUENCY, params)

        response = self.read_response()
        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_SET_FREQUENCY:
                return True

        return False

    def set_min_gating_distance(self, distance_meters):
        """
        Set the minimum gating distance
        :param distance_meters: Distance in meters (10-20000)
        :return: True if successful, False otherwise
        """
        if not 10 <= distance_meters <= 20000:
            raise ValueError("Distance must be between 10 and 20000 meters")

        # Split distance into high and low bytes
        high_byte = (int(distance_meters) >> 8) & 0xFF
        low_byte = int(distance_meters) & 0xFF

        params = [high_byte, low_byte]
        self.send_command(self.CMD_SET_MIN_DISTANCE, params)

        response = self.read_response()
        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_SET_MIN_DISTANCE:
                return True

        return False

    def query_min_gating_distance(self):
        """
        Query the minimum gating distance setting
        :return: Distance in meters or None on failure
        """
        self.send_command(self.CMD_QUERY_MIN_DISTANCE)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_QUERY_MIN_DISTANCE and len(parsed['params']) == 2:
                high_byte, low_byte = parsed['params']
                distance = high_byte * 256 + low_byte
                return distance

        return None

    def set_max_gating_distance(self, distance_meters):
        """
        Set the maximum gating distance
        :param distance_meters: Distance in meters (10-20000)
        :return: True if successful, False otherwise
        """
        if not 10 <= distance_meters <= 20000:
            raise ValueError("Distance must be between 10 and 20000 meters")

        # Split distance into high and low bytes
        high_byte = (int(distance_meters) >> 8) & 0xFF
        low_byte = int(distance_meters) & 0xFF

        params = [high_byte, low_byte]
        self.send_command(self.CMD_SET_MAX_DISTANCE, params)

        response = self.read_response()
        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_SET_MAX_DISTANCE:
                return True

        return False

    def query_max_gating_distance(self):
        """
        Query the maximum gating distance setting
        :return: Distance in meters or None on failure
        """
        self.send_command(self.CMD_QUERY_MAX_DISTANCE)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_QUERY_MAX_DISTANCE and len(parsed['params']) == 2:
                high_byte, low_byte = parsed['params']
                distance = high_byte * 256 + low_byte
                return distance

        return None

    def query_fpga_version(self):
        """
        Query FPGA software version
        :return: Version information dict or None on failure
        """
        self.send_command(self.CMD_QUERY_FPGA_VERSION)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_QUERY_FPGA_VERSION and len(parsed['params']) == 4:
                version_byte, date, month_year, author = parsed['params']

                major = (version_byte >> 4) & 0x0F
                minor = version_byte & 0x0F

                month = (month_year >> 4) & 0x0F
                year = 2020 + (month_year & 0x0F)

                authors = {
                    0x6C: "cliu",
                    0x5D: "dwu", 
                    0xCC: "cycheng"
                }
                author_name = authors.get(author, f"Unknown(0x{author:02X})")

                return {
                    'version': f"V{major}.{minor}",
                    'date': date,
                    'month': month,
                    'year': year,
                    'author': author_name
                }

        return None

    def query_mcu_version(self):
        """
        Query MCU software version
        :return: Version information dict or None on failure
        """
        self.send_command(self.CMD_QUERY_MCU_VERSION)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_QUERY_MCU_VERSION and len(parsed['params']) == 4:
                version_byte, date, month_year, author = parsed['params']

                major = (version_byte >> 4) & 0x0F
                minor = version_byte & 0x0F

                month = (month_year >> 4) & 0x0F
                year = 2020 + (month_year & 0x0F)

                authors = {
                    0x00: "jyang",
                    0xF1: "llfu", 
                    0x01: "zqxiong"
                }
                author_name = authors.get(author, f"Unknown(0x{author:02X})")

                return {
                    'version': f"V{major}.{minor}",
                    'date': date,
                    'month': month,
                    'year': year,
                    'author': author_name
                }

        return None

    def query_hardware_version(self):
        """
        Query hardware version
        :return: Version information dict or None on failure
        """
        self.send_command(self.CMD_QUERY_HARDWARE_VERSION)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_QUERY_HARDWARE_VERSION and len(parsed['params']) == 4:
                mbvs, ctvs, apdvs, ldvs = parsed['params']

                def decode_version(v):
                    major = (v >> 4) & 0x0F
                    minor = v & 0x0F
                    return f"V{major}.{minor}"

                return {
                    'motherboard': decode_version(mbvs),
                    'control_board': decode_version(ctvs),
                    'detection_board': decode_version(apdvs),
                    'driver_board': decode_version(ldvs)
                }

        return None

    def query_sn_number(self):
        """
        Query serial number
        :return: Serial number information dict or None on failure
        """
        self.send_command(self.CMD_QUERY_SN_NUMBER)
        response = self.read_response()

        if response:
            parsed = self._parse_response(response)
            if parsed and parsed['command_code'] == self.CMD_QUERY_SN_NUMBER and len(parsed['params']) == 3:
                month_year, num_high, num_low = parsed['params']

                month = (month_year >> 4) & 0x0F
                year = 2020 + (month_year & 0x0F)

                sn = (num_high << 8) | num_low

                return {
                    'month': month,
                    'year': year,
                    'serial_number': f"{year:04d}{month:02d}{sn:04d}"
                }

        return None

    def _decode_ranging_status_extended(self, status):
        """
        Extended decode of the ranging status byte that also returns whether this is a multi-target reading
        """
        # Determine if this is multi-target mode based on upper 4 bits
        upper_nibble = (status >> 4) & 0x0F
        lower_nibble = status & 0x0F
        is_multi_target = upper_nibble > 0  # If target number is greater than 0, it's multi-target mode
        
        if is_multi_target:
            # Multi-target mode - upper nibble is target number, lower nibble is target type
            target_num = upper_nibble
            target_type = lower_nibble
            
            if target_type == 0x0:
                target_desc = "Single target"
            elif target_type == 0x1:
                target_desc = "Front target"
            elif target_type == 0x2:
                target_desc = "Rear target"
            elif target_type == 0x3:
                target_desc = "Front and rear targets"
            elif target_type == 0x4:
                target_desc = "Out of range"
            else:
                target_desc = f"Reserved (0x{target_type:02X})"
            
            return f"Target #{target_num}: {target_desc}", True
        else:
            # Single/first/last target mode - lower nibble determines target type
            if lower_nibble == 0x00:
                return "Single target", False
            elif lower_nibble == 0x01:
                return "Front target detected", False
            elif lower_nibble == 0x02:
                return "Rear target detected", False
            elif lower_nibble == 0x03:
                return "Reserved", False
            elif lower_nibble == 0x04:
                return "Out of range", False
            elif lower_nibble == 0x05:
                return "Reserved", False
            else:
                return f"Unknown status (0x{status:02X})", False
