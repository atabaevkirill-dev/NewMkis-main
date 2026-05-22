# 3km Eye-Safe Laser Rangefinder Desktop Application

A desktop application for controlling and monitoring a 3km eye-safe laser rangefinder module operating at 1535nm wavelength.

## Features

- Connect to the laser rangefinder module via UART (TTL_3.3V) or TCP/IP
- Support for single and continuous ranging modes
- Configurable ranging parameters (frequency, min/max distance)
- Target selection (first, last, multi-target)
- Real-time distance measurements display
- Device information queries (FPGA/MCU/Hardware versions, serial number)
- Comprehensive logging of operations

## Requirements

- Python 3.7 or higher
- PyQt5
- PySerial

## Installation

1. Clone or download this repository
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

1. Connect your laser rangefinder module to your computer via the serial interface or TCP/IP
2. Run the application:

```bash
python main.py
```

3. Select the connection type (Serial or TCP/IP)
4. For Serial connection: select the correct serial port and baud rate
5. For TCP/IP connection: enter the IP address (default 192.168.1.7) and port (default 20108)
6. Click "Connect" to establish communication with the device
7. Configure ranging parameters as needed
8. Start ranging by selecting the mode and clicking "Start Ranging"

## Device Specifications

- **Eye Safety**: Class I (safe for human eyes)
- **Wavelength**: 1535±5nm
- **Maximum Range**: 
  - Car targets: ≥3500m
  - Building targets: ≥4200m
  - Human targets: ≥2000m
  - UAV targets: ≥1000m
- **Minimum Range**: 15m
- **Accuracy**: ±1m
- **Frequency**: 1-10 Hz
- **Supply Voltage**: DC 4.5-16V
- **Weight**: 32±1g
- **Dimensions**: 48×31×21mm

## Communication Protocol

The application communicates with the rangefinder module using either UART at TTL_3.3V levels or TCP/IP with the following default settings:

### Serial Settings:
- Baud Rate: 115200 (also supports 57600, 9600)
- Data Format: n, 8, 1, MSB first

### TCP/IP Settings:
- IP Address: 192.168.1.7 (default)
- Port: 20108 (default)

The protocol uses packets with the following format:

```
Frame Head (2 bytes): 0xEE 0x16
Data Length (1 byte): 2-6 (total length of next 3 segments)
Device Code (1 byte): 0x03 (fixed value)
Command Code (1 byte): 0-255
Command Parameters (0-4 bytes): 0-255
Checksum (1 byte): Sum of device code, command code and parameters (lower 8 bits)
```

## Supported Commands

- Equipment self-check
- Single ranging
- Set First/Last/Multiple targets
- Continuous ranging
- Stop ranging
- Set baud rate
- Set ranging frequency
- Set min/max gating distances
- Query device information (versions, serial numbers)

## Troubleshooting

- Ensure proper wiring between the rangefinder module and your computer
- For TCP/IP, ensure the IP address and port are correct
- Verify that the correct serial port is selected
- Check that the supply voltage is within the specified range
- Make sure the rangefinder module has sufficient time to initialize after power-on (about 0.5 seconds)

## Safety Notes

- Though the device is eye-safe (Class I), avoid direct viewing of the laser beam
- Follow all local regulations regarding laser equipment
- Do not operate in conditions that could cause the laser to reflect into eyes

## License

This project is licensed under the MIT License - see the LICENSE file for details.