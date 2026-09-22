# ONCAM repository guide for coding agents

Read this file before changing the project. Detailed product context is in `docs/PROJECT_CONTEXT.md`; Tauri setup is in `desktop/README.md`.

## Product goal

The application's display name is **MKIS100TEST** (the project was historically called ONCAM). Internal identifiers keep `oncam` / `ru.oncam.cockpit` on purpose: changing them would orphan saved config (app config dir) and keychain entries.

ONCAM/MKIS100TEST is an operator workstation for aligning the optical axis of CAM 01 with the thermal reference axis of CAM 02. It also tests and controls the TL.0009 pan/tilt platform, cameras, rangefinder and Relay X3, and will record both video channels with device metadata.

## Repository layout

- `desktop/`: the application, Tauri 2 + Rust + React + TypeScript. The former Python/PyQt client was removed in v0.2.0 (see tag `v0.1.0` in git history).
- `desktop/src-tauri/src/video.rs` (RTSP), `onvif.rs` (zoom/focus), `record.rs` + `split.rs` + `mp4fix.rs` (recording), `desktop/src/VideoSurface.tsx`, `alignment.ts`, `splitRecorder.ts`.
- `desktop/docs/`: TL.0009 service subset and factory protocol, rangefinder and Relay X3 protocols (the latter two are reference material not yet implemented beyond TCP reachability).
- `desktop/src-tauri/src/lib.rs`: native config (atomic write, corruption recovery), keychain, device probing, persistent TL.0009 service link with jog watchdog, rocking profiles; unit tests with a mock TL.0009.
- `desktop/src/App.tsx`: cockpit shell — top bar, video stage, status bar.
- `desktop/src/CameraDrawer.tsx`, `desktop/src/SystemDrawer.tsx`: camera drawers (network, lens, reticles) and the top drawer (device modules, TL.0009, tests, recording).
- `desktop/src/config.ts`: config defaults, schema migration and device-module helpers.
- `desktop/src/useJog.ts`: hold-to-move (dead-man) jog; `desktop/src/Reticle.tsx`: reticle rendering.
- `desktop/src/report.ts`, `desktop/src/PrintReport.tsx`: operability protocol (A4, printed to PDF) built only from executed checks.
- `desktop/src/api.ts`: typed boundary between UI and Tauri commands.
- `.github/workflows/desktop.yml`: CI checks and installers for Windows/macOS/Linux; tags `v*` publish a GitHub Release.
- `desktop/docs/TL0009_SERVICE.md`: service-command subset used by the new client.


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
- TL.0009 default project profile: `192.168.1.115:9760` (verified on the device: the service protocol answers only on 9760; 9761/9762 accept TCP but stay silent).
- Rangefinder: `192.168.1.7:20108`.
- Relay X3 fallback: `192.168.127.254:9762`.

TL.0009 movement in the new client must use only the ASCII service protocol (`$...#`). Do not add Pelco-D movement for TL.0009. The factory manual shows management port 9760, Pelco-D 9761 and RS-485 9762, and on this installation the service protocol answers on 9760 (configs saved with 9762 are migrated to 9760 in schema 4). Preserve port configurability.

PAN commands are lower-case (`m n o p q u w x`); TILT commands are upper-case (`M N O P Q U W X`). Validate speeds and angles before sending commands. Stop both axes when a rocking profile is cancelled or fails.

Motion safety in the new client: any STOP (button, Esc, D-pad release) cancels a running profile; jog moves only while the button is held and the native watchdog stops both axes if the UI stops confirming it; all traffic to TL.0009 goes through one serialised link. Profiles use signed angles (PAN ±180°, TILT −45…90°) that are sent as 0.00…359.99° — verify direction and limits on the real platform.

## Security rules

- Never hardcode or commit real passwords.
- Tauri stores camera passwords in the OS keychain. JSON config must not contain them.
- Password reveal is allowed in the UI because the operator requested it, but it must be an explicit temporary action.
- Do not print credential-bearing RTSP URLs.
- Recording metadata may contain IP/protocol/telemetry. Credentials require explicit opt-in and an encrypted manifest; never plaintext.
- Keep `.env`, local config, `node_modules`, `dist`, Cargo `target` and generated schemas out of Git.
- The operability protocol must reflect real results only: never pre-fill, default or simulate a passing check. Unrun checks are «не выполнена», browser-mode protocols carry the «недействителен» warning.

## Current implementation boundary

Implemented: compact cockpit layout, push drawers, resizing/swapping panes, configuration UI with schema migration, OS keychain (native backends), device modules in the summary (add, edit address, hide, remove) with live TCP link status, up to three configurable reticles per camera, TL.0009 service jog (dead-man + watchdog)/stop/self-test, five rocking profiles with progress events, TCP reachability tests, recording settings UI, hover D-pad and mouse lens gestures.

Implemented since: RTSP video — `src-tauri/src/video.rs` (retina, digest auth with the keychain password, no retry after 401 so the camera account is not locked) forwards H.264/H.265 access units over a Tauri channel; `desktop/src/VideoSurface.tsx` decodes them with WebCodecs onto a canvas. Stream path is per camera (`streamPath`): CAM 01 Uniview `/media/video1`, CAM 02 `/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif`. H.265 plays only where the WebView has a hardware HEVC decoder.

Also implemented (needs confirmation on the real hardware): ONVIF lens — `src-tauri/src/onvif.rs`, zoom via PTZ ContinuousMove and focus via Imaging Move, WS-Security digest stamped with the camera clock (both cameras have wrong clocks), plain TCP so system proxies (Hiddify on this PC) are bypassed, watchdog stops the lens 350 ms after the last step, a rejected password is not retried. Recording — `src-tauri/src/record.rs`, fragmented MP4 written from the received access units (no FFmpeg, no transcoding), segments rotate on key frames, optional JSON sidecar without credentials; MKV and the encrypted-secrets manifest are not implemented and shown as such. Alignment — `desktop/src/alignment.ts`, hot target = brightest compact blob, sub-pixel centroid, error = target minus centre of the first enabled reticle in video pixels; CAM 02 must be within tolerance first, «СВЕДЕНО» (white) when both are within `tolerancePx` for `stableMs`.

Video decoding uses WebCodecs with `hardwareAcceleration: "prefer-software"`: measured on these cameras the D3D11 decoder held 5–6 frames and released them in bursts (150–240 ms draw stalls, visible as stutter while the platform moves); software decoding holds ≤2 frames and costs ~7% of one core for both streams. `[diag]` lines in the log appear only on anomalies (pause > 150 ms or dropped frames).

Seeking: recorders write fragmented MP4 while recording (crash-safe) and `src-tauri/src/mp4fix.rs` rewrites each closed MP4 in the background into a regular MP4 with a full index (ftyp+moov+mdat) so Windows players can seek; on failure the fragmented file stays (VLC plays it). Split WebM (only if the webview lacks MP4 MediaRecorder) is not indexed. Recording auto-stop timer: `recording.stopAfterMinutes` (0 = manual). Split recording burns in the reticles when `recording.splitReticles` is on.

Split recording (`desktop/src/splitRecorder.ts` + `src-tauri/src/split.rs`): both panes composed side by side in on-screen order and re-encoded by the webview MediaRecorder (MP4/H.264 when offered, else WebM); chunks are appended natively once a second; files «<product>_<cam>+<cam>_<local time>». It depends on webview timers, so do not minimise the window while it records. Recording layout: separate / split / both. Jog axis inversion (`jog.invertPan`, `jog.invertTilt`) swaps only what the D-pad sends; rocking profiles use absolute angles and are not inverted.

Not yet implemented end-to-end: MKV recording, encrypted secrets manifest, telemetry in recording metadata, live telemetry polling, protocol-level device test adapters. The UI shows `—` or «не подключено» for these instead of sample values; keep it that way. UI placeholders are not evidence that hardware integration is complete. State this accurately in handoffs.

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
cargo test --manifest-path src-tauri/Cargo.toml
cd ..
git diff --check
git status --short
```

Preserve unrelated user changes. Use `apply_patch` for manual edits. Prefer small vertical slices that keep the Tauri client buildable.
