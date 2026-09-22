# MKIS100TEST

Рабочее место оператора для сведения оптической оси CAM 01 с эталонной тепловизионной осью CAM 02, проверки и управления поворотным устройством TL.0009, дальномером и Relay X3. Приложение — [`desktop/`](desktop/README.md) (Tauri 2 + Rust + React). Прежний Python/PyQt-клиент удалён в v0.2.0 и доступен в истории git по тегу `v0.1.0`; описания протоколов перенесены в [`desktop/docs`](desktop/docs).

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
