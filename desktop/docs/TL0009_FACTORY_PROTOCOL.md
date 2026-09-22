# TechLazer Service Protocol Implementation

## Overview
This module implements the TechLazer service protocol that operates on port 9760. It provides comprehensive control over the PTZ unit including absolute positioning, speed control, and system monitoring capabilities.

## Features

### Basic Connection Management
- TCP connection to device at port 9760
- Thread-safe communication
- Automatic reconnection capability
- Proper error handling and logging

### Firmware Commands
- [ ] `$I#` - Get firmware type (`get_firmware_type()`)
- [ ] `$V#` - Get firmware version (`get_firmware_version()`) - Returns version as float (e.g., 1.16)

### Device Configuration
- [ ] `$1#` - Get Pelco-D address (`get_pelco_address()`)
- [ ] `$1,addr#` - Set Pelco-D address (`set_pelco_address(address)`)
- [ ] `$2#` - Get RS-485 baud rate (`get_rs485_baud_rate()`)
- [ ] `$2,baud#` - Set RS-485 baud rate (`set_rs485_baud_rate(baud_rate)`)
- [ ] `$b#` - Get Pelco-D TCP port (`get_pelco_port()`)
- [ ] `$b,port#` - Set Pelco-D TCP port (`set_pelco_port(port)`)
- [ ] `$c#` - Get RS-485 TCP port (`get_rs485_port()`)
- [ ] `$c,port#` - Set RS-485 TCP port (`set_rs485_port(port)`)

### Speed Control
- [ ] `$3#` - Get pan axis speed settings (`get_pan_speed_settings()`)
- [ ] `$3,min,accDec,max#` - Set pan axis speed settings (`set_pan_speed_settings(min_speed, acc_dec, max_speed)`)
- [ ] `$4#` - Get tilt axis speed settings (`get_tilt_speed_settings()`)
- [ ] `$4,min,accDec,max#` - Set tilt axis speed settings (`set_tilt_speed_settings(min_speed, acc_dec, max_speed)`)

### Position Control
- [ ] `$o#` - Get current pan position (`get_current_pan_position()`)
- [ ] `$O#` - Get current tilt position (`get_current_tilt_position()`)
- [ ] `$x#` - Get target pan position and max speed (`get_target_pan_position_and_max_speed()`)
- [ ] `$x,targetPos,maxSpeed#` - Move pan to position (`move_to_pan_position(target_pos, max_speed)`)
- [ ] `$X#` - Get target tilt position and max speed (`get_target_tilt_position_and_max_speed()`)
- [ ] `$X,targetPos,maxSpeed#` - Move tilt to position (`move_to_tilt_position(target_pos, max_speed)`)
- [ ] `$w#` - Get target pan speed (`get_target_pan_speed()`)
- [ ] `$w,targetSpeed#` - Set pan speed (`set_pan_speed(speed)`)
- [ ] `$W#` - Get target tilt speed (`get_target_tilt_speed()`)
- [ ] `$W,targetSpeed#` - Set tilt speed (`set_tilt_speed(speed)`)

### Axis Control
- [ ] `$u#` - Stop pan axis (`stop_pan_axis()`)
- [ ] `$U#` - Stop tilt axis (`stop_tilt_axis()`)
- [ ] `$m#` - Get pan axis state (`get_pan_axis_state()`)
- [ ] `$M#` - Get tilt axis state (`get_tilt_axis_state()`)
- [ ] `$m,1#` - Start pan self-test (`start_pan_self_test()`)
- [ ] `$M,1#` - Start tilt self-test (`start_tilt_self_test()`)

### Limits and Constraints
- [ ] `$7#` - Get pan limits (`get_pan_limits()`)
- [ ] `$7,enable,left,right#` - Set pan limits (`set_pan_limits(enable, left, right)`)
- [ ] `$8#` - Get tilt limits (`get_tilt_limits()`)
- [ ] `$8,left,right#` - Set tilt limits (`set_tilt_limits(left, right)`)

### System Monitoring
- [ ] `$t#` - Get current temperature (`get_current_temperature()`)
- [ ] `$0#` - Get supply voltage (`get_supply_voltage()`)
- [ ] `$h#` - Get heater status (`get_heater_status()`)
- [ ] `$hE#` - Enable heater manually (`enable_heater_manual()`)
- [ ] `$hD#` - Disable heater manually (`disable_heater_manual()`)

### Network Settings
- [ ] `$a#` - Get network settings (`get_network_settings()`)
- [ ] `$a,dhcp,ip,mask,gateway,dns#` - Set network settings (`set_network_settings(dhcp, ip, mask, gateway, dns)`)

### System Control
- [ ] `$d#` - Factory reset (`factory_reset()`)
- [ ] `$e#` - Reboot device (`reboot_device()`)

## Usage Examples

### Basic Usage
```python
from ptz.techlazer_service_protocol import TechLazerServiceProtocol

# Create controller instance
controller = TechLazerServiceProtocol(ip="192.168.1.115", port=9760)

# Connect to device
if controller.connect():
    print("Connected successfully!")
    
    # Get current position
    pan_pos = controller.get_current_pan_position()
    tilt_pos = controller.get_current_tilt_position()
    print(f"Current position - Pan: {pan_pos}°, Tilt: {tilt_pos}°")
    
    # Move to specific position
    controller.move_to_pan_position(180.0, 20.0)  # Move to 180° at max 20°/s
    controller.move_to_tilt_position(45.0, 10.0)  # Move to 45° at max 10°/s
    
    # Close connection
    controller.close()
```

### Integration with PelcoDController
The service protocol is automatically integrated with the existing [PelcoDController](pelcod_controller.py) and can be accessed via the `service_protocol` property:

```python
from ptz.pelcod_controller import PelcoDController

# Create controller with service protocol integration
controller = PelcoDController(ip="192.168.1.115", port=9761)

# Access service protocol functionality
pan_pos, tilt_pos = controller.get_current_positions()
pan_state, tilt_state = controller.get_axis_states()

# Move to absolute positions
controller.move_pan_absolute(90.0, 15.0)   # Move to 90° at max 15°/s
controller.move_tilt_absolute(30.0, 8.0)   # Move to 30° at max 8°/s

# Get system information
info = controller.get_service_protocol_info()
```

## Requirements
- Python 3.6+
- Standard library only (no external dependencies)

## Thread Safety
The implementation includes thread safety mechanisms for concurrent access to the TCP connection using locks and proper synchronization.

## Error Handling
Comprehensive error handling is implemented with:
- Connection timeouts
- Retry mechanisms
- Graceful degradation
- Detailed logging