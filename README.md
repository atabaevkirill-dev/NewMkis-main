# MKIS100TEST

Рабочее место оператора для сведения оптической оси CAM 01 с эталонной тепловизионной осью CAM 02, проверки и управления поворотным устройством TL.0009, дальномером и Relay X3. Активное приложение — [`desktop/`](desktop/README.md) (Tauri 2 + Rust + React).

## Скачать готовое приложение

Страница **Releases** этого репозитория на GitHub → последняя версия:

| Система | Файл |
|---|---|
| Windows 10/11 | `MKIS100TEST_<версия>_x64-setup.exe` — установщик; `…_x64-portable.exe` — без установки; `.msi` |
| macOS | `MKIS100TEST_<версия>_universal.dmg` |
| Linux | `.AppImage`, `.deb`, `.rpm` |

Сборки не подписаны: при первом запуске Windows SmartScreen («Подробнее → Выполнить в любом случае») и macOS Gatekeeper («Открыть» из контекстного меню) покажут предупреждение. Установщики для каждого коммита также лежат в **Actions** → запуск workflow «MKIS100TEST» → Artifacts.

## Склонировать и собрать

```bash
git clone https://github.com/atabaevkirill-dev/NewMkis-main.git
cd NewMkis-main/desktop
npm ci
npm run dev:native      # запуск для разработки
npm run tauri build     # установщики для текущей ОС в src-tauri/target/release/bundle
```

Требования и подробности — в [desktop/README.md](desktop/README.md).

## Выпуск новой версии

1. Поднять `version` в `desktop/package.json`, `desktop/src-tauri/tauri.conf.json` и `desktop/src-tauri/Cargo.toml`.
2. `git tag v0.2.0 && git push origin v0.2.0`.
3. Workflow [.github/workflows/desktop.yml](.github/workflows/desktop.yml) соберёт Windows, macOS и Linux и опубликует релиз.

---

## Старое PyQt-приложение (эталон аппаратной логики)

Сохраняется до проверки всех аппаратных функций в новом клиенте.

OnCam is a Python application that provides camera monitoring and PTZ (Pan-Tilt-Zoom) control system with support for both ONVIF PTZ cameras and Pelco-D protocol pan-tilt units.

### Features

- Dual Camera RTSP Streaming - Displays video from two IP cameras side-by-side
- PTZ Control - Supports both ONVIF PTZ cameras and Pelco-D protocol pan-tilt units
- Crosshair Overlay - Optional crosshairs for targeting and positioning
- Keyboard Controls - Arrow keys, zoom controls, and speed adjustment
- Configuration Management - Saves settings to a JSON file
- Standalone Executable - Can be packaged as a standalone executable for distribution

### Requirements

- Python 3.7 or higher
- Windows, macOS, or Linux operating system

### Installation

1. Clone or download this repository to your local machine
2. Navigate to the project directory in your terminal/command prompt
3. Install the required dependencies:

```bash
python install_requirements.py
```

Alternatively, you can install dependencies manually:

```bash
pip install -r requirements.txt
```

### Usage

To run the application:

```bash
python -m core.run_app
```

Or directly:

```bash
python -m core.main
```

### Creating a Standalone Executable

To package the application as a standalone executable for distribution:

### Method 1: Using the build script
```bash
python build_exe.py
```

### Method 2: Using PyInstaller directly
```bash
pyinstaller oncam_app.spec
```

After successful build, the executable will be located in the `dist/` folder. The executable contains all necessary dependencies and can run on Windows systems without Python installed.

For more detailed instructions, see BUILD_INSTRUCTIONS.md

### Configuration

The application stores settings in JSON format in your user directory under `OnCamLogs/config.json`.
You can configure:

- Camera IP addresses, ports, and credentials
- Display preferences (crosshairs, PTZ panels visibility)
- Control settings (speed delays, zoom delays)

### Controls

- Arrow Keys: Pan/Tilt
- Page Up: Zoom In
- Page Down: Zoom Out
- Space: Stop All Movement
- + (Plus): Increase Speed
- - (Minus): Decrease Speed
- Ctrl+X: Toggle Crosshairs
- Ctrl+P: Toggle PTZ Controls
- Ctrl+I: Toggle Invert Tilt
- F11: Toggle Fullscreen Mode

### Troubleshooting

If you encounter issues with ONVIF cameras due to missing WSDL files:

1. Make sure you have properly installed the `onvif_zeep` package
2. The application will attempt to work without WSDL files by using default ONVIF initialization
3. Check camera credentials and network connectivity

### Project Structure

```
NewMkis/
├── main.py                 # Main application entry point
├── config_manager.py       # Configuration management
├── video_thread.py         # Video streaming thread
├── ptz_controller.py       # ONVIF PTZ controller
├── settings_dialog.py      # Settings dialog
├── pelcod_controller.py    # Pelco-D protocol controller
├── video_widget.py         # Video display widget
├── ui/
│   └── main_window.py      # Main window implementation
├── requirements.txt        # Python dependencies
├── install_requirements.py # Installation script
├── run_app.py             # Application runner with dependency check
├── oncam_app.spec         # PyInstaller spec file for executable creation
├── build_exe.py           # Build script for executable creation
├── BUILD_INSTRUCTIONS.md  # Instructions for executable creation
└── README.md             # This file
```

### License

This project is created for personal/educational use.
