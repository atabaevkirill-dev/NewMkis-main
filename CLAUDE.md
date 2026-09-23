# Claude Code context

Read `AGENTS.md` first, then `docs/PROJECT_CONTEXT.md` and `desktop/README.md`. `AGENTS.md` is the canonical source for product constraints, hardware protocols, security rules, current implementation status and validation commands. Do not treat visible UI placeholders as completed hardware integration.

This file adds how to work on the project day to day: the machine, the lab, diagnostics and releases.

## Working with the owner

- Answer in Russian. Messages sometimes arrive typed in the English layout (`ntgkbrb` = «теплики», `lfdfq` = «давай»): decode them instead of asking.
- Commits go straight to `main`. A release is an annotated tag `vX.Y.Z` pushed to GitHub: CI builds the installers and publishes the Release. The repo-local git identity is already configured; do not change it.
- The owner enters camera passwords in the UI. Never type, read back or print a password, even one pasted in chat.

## This machine (Windows 11, lab PC 192.168.1.100)

- Git Bash and PowerShell. `python` is not on PATH: script with `node`. Git Bash rewrites arguments starting with `/` into `C:/Program Files/Git/…`: use `MSYS_NO_PATHCONV=1` or drop the leading slash.
- A system proxy (Hiddify, 127.0.0.1:12334) answers HTTP to the cameras with 502: use `curl --noproxy '*'`. The app's ONVIF client uses raw TCP for the same reason.
- `gh` is not authenticated: read CI runs and releases through the GitHub REST API with `curl` (60 requests an hour).

## Lab hardware (as of v0.2.3)

Units are swapped on the stand: other cameras and platforms appear at the same addresses (check MAC addresses with `arp -a`), thermal cameras change. The app finds ONVIF cameras itself; `real_network` below shows what answers.

| Device | Address | Notes |
|---|---|---|
| CAM 01 Uniview UV-ZNH2130M | `192.168.1.68` | ONVIF path `/Stream/Live/101?…` (1280×720 H.264), `/media/video1` also works. Zoom by absolute position (grid ≈ 1/3300 of the range), focus by pulses (Imaging continuous speed range −7…7) |
| CAM 02 thermal, Dahua family («IP_Camera») | `192.168.1.108` | 640×512 H.264, ONVIF path `/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif`; zoom by position, relative focus |
| CAM 02 alternative: thermal via Beward B102S | `192.168.1.99` | RTSP `/av0_0`. Clock stuck around 2010. Relative zoom/focus only (`GetStatus` fails), every lens command answers after ≈ 1 s |
| TL.0009 | `192.168.1.115:9760` | service protocol answers only on 9760 |

A second Beward sits at its factory address `192.168.0.99` (another subnet, unreachable from this PC). Camera clocks are wrong: ONVIF requests are stamped with the camera clock.

## Run and observe

- Checks, same as CI: `cd desktop && npm run check && cargo test --manifest-path src-tauri/Cargo.toml`.
- App: `cd desktop && npm run dev:native > ../../tauri-dev.log 2>&1` in the background, one instance only (Vite port 1420). Native log prefixes: `[video]`, `[onvif]`, `[discovery]`, `[record]`, `[diag]`.
- Vite HMR does not restart the video pipeline: restart the app after decoder or stream changes.
- Config: `%APPDATA%\ru.oncam.cockpit\config.json`. Edit it only while the app is closed, and keep a backup. Passwords: Windows Credential Manager, `camera1.ru.oncam.cockpit` and `camera2.ru.oncam.cockpit`.
- Installed build: per-user NSIS in `%LOCALAPPDATA%\MKIS100TEST`. Upgrade with the release `*_x64-setup.exe /S` while the app is closed, after checking its SHA-256 against the asset digest from the GitHub API.

## Hardware diagnostics

Ignored tests in `desktop/src-tauri`, run with `cargo test --lib <name> -- --ignored --nocapture`. They take the password from the keychain and never print it.

| Test | Environment | Effect |
|---|---|---|
| `real_network` | — | WS-Discovery from every interface: which ONVIF cameras answer |
| `real_camera` | `MKIS_ONVIF=camera1@192.168.1.68:80` | read-only: services, media profiles, stream URI, move spaces, call timings |
| `real_zoom_steps` | `MKIS_ONVIF`, `MKIS_STEP=0.1`, `MKIS_COUNT=3` | **moves the zoom** forward and back: say so before running |
| `depacketize_real_stream` | `MKIS_RTP=camera2@rtsp://192.168.1.99:554/av0_0` | 90 s through the depacketizer, first error if any |
| `dump_raw_rtp` | `MKIS_RTP` | 60 s of raw RTP, looks for `00 00 00 xx` |
| `real_file` | `MKIS_DEFRAG=<copy.mp4>` | re-indexes a recording in place: use a copy |

Measure before changing: timings and positions read from the devices settled every lens and stream question in this project.

## Lessons learned

- After a 401 the app stops retrying (stream and lens): Uniview locks the account after a few failures. Never brute-force passwords or stream paths.
- An RTSP server answers 401 before it looks at the path: without the password, stream paths cannot be probed.
- Beward's «Incorrect password type» meant a wrong WS-Security timestamp, not a wrong token type.
- `desktop/src-tauri/vendor/retina` is retina 0.4.20 with one patch (see `vendor/retina/MKIS100TEST.md`); re-apply it when updating retina.
- The version lives in five places: `desktop/package.json`, `desktop/package-lock.json` (two entries), `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml` and the `oncam-desktop` entry of `desktop/src-tauri/Cargo.lock`.
