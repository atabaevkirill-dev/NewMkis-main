# ONCAM repository guide for coding agents

Read this file before changing the project. Detailed product context is in `docs/PROJECT_CONTEXT.md`; Tauri setup is in `desktop/README.md`.

## Product goal

ONCAM is an operator workstation for aligning the optical axis of CAM 01 with the thermal reference axis of CAM 02. It also tests and controls the TL.0009 pan/tilt platform, cameras, rangefinder and Relay X3, and will record both video channels with device metadata.

## Repository layout

- `desktop/`: active rewrite, Tauri 2 + Rust + React + TypeScript.
- `camera/`, `ptz/`, `rangefinder/`, `relayx3/`, `ui/`, `core/`: legacy PyQt/Python implementation and hardware reference code.
- `desktop/src-tauri/src/lib.rs`: native config, keychain, discovery, TL.0009 service TCP commands and rocking profiles.
- `desktop/src/App.tsx`: current cockpit UI and interactions.
- `desktop/src/api.ts`: typed boundary between UI and Tauri commands.
- `desktop/docs/TL0009_SERVICE.md`: service-command subset used by the new client.

Do not delete the Python implementation until its hardware behavior has been reproduced and verified in Tauri.

## Non-negotiable UX rules

1. CAM 01 and CAM 02 form one uninterrupted video surface.
2. Their divider is draggable; cameras can be swapped.
3. Left drawer contains CAM 01 settings; right drawer contains CAM 02 settings.
4. Top drawer contains system summary, TL.0009, tests and recording.
5. Drawers must push/resize video. They must never overlay or block it.
6. No page scrolling. Keep the interface compact and usable at the configured minimum window size.
7. No green accent. Use neutral white/gray plus blue for CAM 01 and amber for CAM 02.
8. Persistent telemetry appears only in the bottom status bar. Do not duplicate it in video panes.
9. Video panes stay clean. Optional camera OSD may show only camera name, FPS and ONVIF state.
10. D-pad appears on video hover and shows only its buttons, without a titled container.
11. Wheel over a video pane controls that camera's ONVIF zoom.
12. Right mouse button + wheel controls that camera's ONVIF focus; suppress the context menu over video.
13. Alignment success is white, not green. CAM 02 is the reference. Default success rule: error within 3 px for 1.2 s.

## Hardware and protocols

- CAM 01 default: `192.168.1.68`, ONVIF `80`, RTSP `554`.
- CAM 02 default: `192.168.1.108`, ONVIF `80`, RTSP `554`.
- TL.0009 default project profile: `192.168.1.115:9762`.
- Rangefinder: `192.168.1.7:20108`.
- Relay X3 fallback: `192.168.127.254:9762`.

TL.0009 movement in the new client must use only the ASCII service protocol (`$...#`). Do not add Pelco-D movement for TL.0009. The factory manual shows management port 9760, Pelco-D 9761 and RS-485 9762, but this installation explicitly uses configurable port 9762 for its working service profile. Preserve port configurability.

PAN commands are lower-case (`m n o p q u w x`); TILT commands are upper-case (`M N O P Q U W X`). Validate speeds and angles before sending commands. Stop both axes when a rocking profile is cancelled or fails.

## Security rules

- Never hardcode or commit real passwords.
- Tauri stores camera passwords in the OS keychain. JSON config must not contain them.
- Password reveal is allowed in the UI because the operator requested it, but it must be an explicit temporary action.
- Do not print credential-bearing RTSP URLs.
- Recording metadata may contain IP/protocol/telemetry. Credentials require explicit opt-in and an encrypted manifest; never plaintext.
- Keep `.env`, local config, `node_modules`, `dist`, Cargo `target` and generated schemas out of Git.

## Current implementation boundary

Implemented: cockpit layout, push drawers, resizing/swapping panes, configuration UI, keychain commands, configured-device TCP discovery, TL.0009 service jog/stop/self-test, five rocking profiles, test/recording UI, hover D-pad and mouse lens gestures.

Not yet implemented end-to-end: RTSP decode/render, full ONVIF zoom/focus adapter, FFmpeg recording, live telemetry polling, automatic axis-error computer vision, complete device test adapters. UI placeholders are not evidence that hardware integration is complete. State this accurately in handoffs.

## Development workflow

```bash
cd desktop
npm ci
npm run doctor
npm run check
npm run dev:native
```

For browser-only UI work use `npm run dev` and `http://127.0.0.1:1420`. Never open `desktop/index.html` via `file://`.

Before committing:

```bash
cd desktop
npm run check
cd ..
git diff --check
git status --short
```

Preserve unrelated user changes. Use `apply_patch` for manual edits. Prefer small vertical slices that leave both the legacy application and the Tauri client buildable.
