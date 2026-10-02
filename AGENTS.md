# ONCAM repository guide for coding agents

Read this file before changing the project. Detailed product context is in `docs/PROJECT_CONTEXT.md`; Tauri setup is in `desktop/README.md`.

## Product goal

The application's display name is **MKIS100TEST** (the project was historically called ONCAM). Internal identifiers keep `oncam` / `ru.oncam.cockpit` on purpose: changing them would orphan saved config (app config dir) and keychain entries.

ONCAM/MKIS100TEST is an operator workstation for aligning the optical axis of CAM 01 with the thermal reference axis of CAM 02. It also tests and controls the TL.0009 pan/tilt platform, cameras, rangefinder and Relay X3, and will record both video channels with device metadata.

## Repository layout

- `desktop/`: the application, Tauri 2 + Rust + React + TypeScript. The former Python/PyQt client was removed in v0.2.0 (see tag `v0.1.0` in git history).
- `desktop/src-tauri/src/video.rs` (RTSP), `onvif.rs` (zoom/focus, stream address), `discovery.rs` (WS-Discovery), `record.rs` + `split.rs` + `mp4fix.rs` (recording), `thermal.rs` (camera temperatures over HTTP), `desktop/src/VideoSurface.tsx`, `alignment.ts`, `splitRecorder.ts`, `thermal.ts` + `ThermalLayer.tsx` (palettes, measuring points, thermal settings).
- `desktop/docs/`: TL.0009 service subset and factory protocol, rangefinder protocol and its use in the app (`RANGEFINDER_PROTOCOL.md`), Relay X3 protocol (reference material not yet implemented beyond TCP reachability).
- `desktop/src-tauri/src/rangefinder.rs` (rangefinder link, commands, continuous-ranging watchdog), `desktop/src/rangefinder.ts` (readings, the distance at the reticle).
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

1. CAM 01 and CAM 02 form one uninterrupted video surface. The operator may show one camera alone (top bar: CAM 01 / both / CAM 02, saved as `view`; or drag the divider into the last 12 % at an edge to hide the squeezed camera; or the × that appears in a pane's corner on hover, which turns into «both» while that pane is alone); the hidden camera keeps streaming, so recording and its overlays go on. Alignment needs both panes shown.
2. Their divider is draggable; cameras can be swapped.
3. The left drawer holds the settings of the camera shown on the left, the right drawer those of the camera on the right (CAM 01 left, CAM 02 right by default). Swapping the panes moves the settings toggles, the drawers and the view switch with them; accents stay with the cameras.
4. Top drawer contains system summary, TL.0009, tests and recording.
5. Drawers must push/resize video. They must never overlay or block it.
6. No page scrolling. Keep the interface compact and usable at the configured minimum window size.
7. No green accent. Use neutral white/gray plus blue for CAM 01 and amber for CAM 02.
8. Persistent telemetry appears only in the bottom status bar. Do not duplicate it in video panes. The one exception is the rangefinder distance next to the reticle (as in a rangefinder sight), shown on the panes chosen in its settings.
9. Video panes stay clean. Optional camera OSD may show only camera name, FPS and ONVIF state. The thermal pane (CAM 02) may also show the thermal overlay the operator switches on in its drawer: up to three measuring points, the hottest/coldest-point markers and the palette scale. Their temperatures come only from the camera; without an answer they show «—».
10. D-pad appears on video hover and shows only its buttons, without a titled container.
11. Wheel over a video pane controls that camera's ONVIF zoom.
12. Right mouse button + wheel controls that camera's ONVIF focus; suppress the context menu over video.
13. Alignment success is white, not green. CAM 02 is the reference. Default success rule: error within 3 px for 1.2 s.
14. A pane without a live picture (stream off, connecting, in error, or no frame drawn for 2 s) shows only «НЕТ СИГНАЛА» with the reason and the camera address: no placeholder imagery, no frozen last frame, no reticles. The stale frame is cleared, so alignment never measures it.

## Hardware and protocols

- CAM 01 default: `192.168.1.68`, ONVIF `80`, RTSP `554`.
- CAM 02 thermal camera on the stand (as of v0.2.5): OEM «General IP Camera» (Dahua-family firmware 1.030, iRay FT640 core, 640×512), radiometric. Its firmware keeps ONVIF users apart from web users: ONVIF/RTSP may accept a password that the web interface and the HTTP API refuse, so the drawer has a separate «Пароль веб-интерфейса». A wrong web password is answered with HTTP 200 `Error … Invalid Authority!` (a malformed request gets the same answer); after five of them the camera answered 401, i.e. locked the web account.
- CAM 02 default: `192.168.1.108` (Dahua-family factory address), RTSP `554` — whichever thermal camera is fitted: different units are swapped in, and the app finds and adopts them (see below). Seen so far: a Dahua-family thermal ("IP_Camera", 640×512 H.264, ONVIF path `/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif`) and an analogue thermal camera behind a Beward B102S video server (`/av0_0`). The B102S clock is years off; a WS-Security stamp from the PC clock is refused with the misleading fault "Incorrect password type", the camera-clock stamp is accepted. It advertises PTZ and Imaging (relative zoom and focus, both at `/onvif/device_service`); whether they drive the thermal lens depends on how the lens is wired to the encoder.
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

Implemented since: RTSP video — `src-tauri/src/video.rs` (retina, digest auth with the keychain password, no retry after 401 so the camera account is not locked) forwards H.264/H.265 access units over a Tauri channel; `desktop/src/VideoSurface.tsx` decodes them with WebCodecs onto a canvas. The stream path is asked from the camera over ONVIF `GetStreamUri` before every connection (`streamAuto`, default on; first H.264 media profile, since the webview cannot decode H.265 everywhere); `streamPath` is the path used without `streamAuto` and the fallback with it. Camera discovery — `src-tauri/src/discovery.rs`, WS-Discovery from every local IPv4 interface (the lab PC has two network cards and its default route does not face the cameras); the camera drawer lists what answered. A streaming camera in error whose address no longer answers (absent from discovery and closed on its ONVIF port) is replaced by the only unclaimed camera in the PC subnets, and that change alone is saved (`findReplacement` in `App.tsx`); several candidates or a camera in another subnet are only reported. A new camera still needs its password once. See `desktop/docs/RTSP_CAMERAS.md`. H.265 plays only where the WebView has a hardware HEVC decoder.

Also implemented (needs confirmation on the real hardware): ONVIF lens — `src-tauri/src/onvif.rs`, one discrete step per wheel notch or button press (per camera: `zoomStepPercent`, default 0.1 %, and `focusStepPercent`, default 2 %, of the lens range; 0.01–25 %). Zoom prefers PTZ AbsoluteMove to a target accumulated natively (read back with GetStatus after 2 s idle, +1e-6 for the 6-decimal report): cameras round every target down to their grid (CAM 01: 1/3300 of the range, ~0.03 %), so relative steps below a cell never move forward and always move back, while the accumulated target is symmetric (verified on CAM 01: 0.01 % steps, exact round trip, 20–40 ms per command). Then PTZ RelativeMove / Imaging relative Move when advertised (CAM 02 Beward: relative only, GetStatus fails with "No such ProfileToken", each PTZ command answers after ~1 s), otherwise a ContinuousMove pulse of 40 ms per percent that is stopped explicitly and carries a PTZ timeout; steps arriving while a command runs are merged (`desktop/src/lens.ts`); HTTP responses end at Content-Length / last chunk instead of waiting for the socket to close; WS-Security digest stamped with the camera clock (both cameras have wrong clocks), plain TCP so system proxies (Hiddify on this PC) are bypassed, a watchdog stops any move whose stop failed, a rejected password is not retried. Recording — `src-tauri/src/record.rs`, fragmented MP4 written from the received access units (no FFmpeg, no transcoding), segments rotate on key frames, optional JSON sidecar without credentials; MKV and the encrypted-secrets manifest are not implemented and shown as such. Alignment — `desktop/src/alignment.ts`, hot target = brightest compact blob, sub-pixel centroid, error = target minus centre of the first enabled reticle in video pixels; CAM 02 must be within tolerance first, «СВЕДЕНО» (white) when both are within `tolerancePx` for `stableMs`.

Video decoding uses WebCodecs with `hardwareAcceleration: "prefer-software"`: measured on these cameras the D3D11 decoder held 5–6 frames and released them in bursts (150–240 ms draw stalls, visible as stutter while the platform moves); software decoding holds ≤2 frames and costs ~7% of one core for both streams. `[diag]` lines in the log appear only on anomalies (pause > 150 ms or dropped frames).

Seeking: recorders write fragmented MP4 while recording (crash-safe) and `src-tauri/src/mp4fix.rs` rewrites each closed MP4 in the background into a regular MP4 with a full index (ftyp+moov+mdat) so Windows players can seek; on failure the fragmented file stays (VLC plays it). Split WebM (only if the webview lacks MP4 MediaRecorder) is not indexed. Recording auto-stop timer: `recording.stopAfterMinutes` (0 = manual). Split recording burns in the reticles when `recording.splitReticles` is on.

Split recording (`desktop/src/splitRecorder.ts` + `src-tauri/src/split.rs`): both panes composed side by side in on-screen order and re-encoded by the webview MediaRecorder (MP4/H.264 when offered, else WebM); chunks are appended natively once a second; files «<product>_<cam>+<cam>_<local time>». It depends on webview timers, so do not minimise the window while it records. Recording layout: separate / split / both. Jog axis inversion (`jog.invertPan`, `jog.invertTilt`) swaps only what the D-pad sends; rocking profiles use absolute angles and are not inverted.

Thermal imaging (CAM 02): false-colour palettes (white/black hot, ironbow, rainbow, rainbow HC, arctic, ice-fire, red hot) are SVG filters applied as CSS `filter` to the video canvas, so the canvas keeps the camera's own white-hot pixels for alignment and extremes; the split recording draws with the same filter. Up to three measuring points (double click places, drag moves, double click removes; positions are fractions of the frame), markers that follow the hottest and coldest point (found in the picture, coarse then full resolution), and a palette scale labelled with those two temperatures. Temperatures come only from the camera: `src-tauri/src/thermal.rs` asks the radiometric HTTP API (`RadiometryManager.cgi?action=getRandomPointTemper&channel=1&coordinate[0]=x&coordinate[1]=y`, 0…8191) twice a second, one request per point (30–60 ms each), with HTTP Digest and the web password (`camera2-web` in the keychain, falling back to the camera password). A refused password stops measuring after one attempt until a password is saved or «Повторить» is pressed; an error answer (the stand camera says «Server internal error» for a while after power-on) pauses polling for 5 s and then asks again (unit tests with mock cameras for both). The stand camera reads 66–68 for a 19–20 °C room although its config says `TemperatureUnit=Centigrade`, `TempRangeMode=High` (high gain, the room-temperature range) and switching `TemperEnable` on changed nothing: either °F-scaled values or an offset of ≈ +46 °C, hence the per-camera unit setting (as labelled / °C / °F); confirm against a reference (a hand reads ≈ 93 if °F, ≈ 80 if offset) before trusting either. The drawer also reads and writes the camera's measuring parameters (`HeatImagingThermometry`: emissivity, distance kept as `ObjectDistance` + `DistanceDecimalPart`, reflected and air temperature, humidity, transmissivity; `configManager.cgi?action=setConfig&HeatImagingThermometry.<key>=<value>` answers `OK`, verified with a same-value write), with typical emissivities of materials. The split recording burns in the thermal overlay (`recording.splitThermal`, drawn by `drawThermalOverlay` like the screen layer).

Picture mirroring per camera (`flipX`, `flipY`; both = 180° turn) is a CSS transform of the canvas. The canvas keeps the camera's own orientation, so everything measured on it is converted: the alignment fix is reported in the picture as shown (reticles are screen overlays), thermal points are stored as shown and converted to the camera's orientation for its API, the split recording draws the picture mirrored. The pass-through recording keeps the camera's orientation. D-pad directions are not tied to mirroring (TL.0009 «Инверт PAN/TILT» does that).

Rangefinder (verified on the stand module, 2026-10-02): one persistent TCP link to the serial-to-TCP converter (`192.168.1.7:20108`, UART frames `EE 16 len 03 cmd … sum`), opened at start by sending the chosen target mode and re-sent whenever the link comes back; a reader thread turns every range reply and fault report into a `rangefinder` event. Single range by button, key R or automatically 0.7 s after a D-pad move ends; continuous ranging 1–10 Hz always has a deadline (native watchdog, default 60 s) and is stopped by «Стоп», the global СТОП/Esc and app exit; first/last/multi target mode; the range gate is read from and written to the module; self-test (one laser pulse) on its tab and in «Тесты», recorded in the protocol; serial, firmware, board versions and pulse counters (no emission). The distance shows on the crosshair as in a rangefinder sight (`RangeReadout.tsx`, SVG): big digits under the first enabled reticle in its colour with a dark halo, target mode and «● N Гц» of continuous ranging above it, further targets listed under the main one, «- - - -» with «нет цели в стробе» when nothing is in the gate, blinking dashes and a pulsing ring while a single range is on its way, dimmed when older than 5 s; on both panes, one or none. It is also in the status bar (RANGE) and is burnt into the split recording with the reticles (`drawRangeDisplay`, same layout). The digits sit at the aiming point whatever the reticle size (inside the gap of a cross when there is room, never farther than 70 px): measuring from the ends of the lines put them off screen with a 2000 px cross. Before the first range the field shows «- - - -» with «R — замер» (or «нет связи с дальномером»). Rangefinder sight (top bar «Дальномер», `RangeSight.tsx` + `sightGeometry.ts`): four styles with the distance built in — tactical mil-dot (fine cross, mil-dots, heavy posts; distance in the lower right quadrant), ACOG-like chevron with stadia, LRF ranging box (corners blink while ranging), holographic collimator (glowing ring and dot, SVG blur; canvas shadow in recordings); colour, size, brightness and the laser aiming point per camera (boresight offset from the pane centre). It replaces the camera reticles on the panes that show the distance, except while alignment is on (alignment measures against the reticles); the split recording draws the same primitives. Hiding the rangefinder in the summary stops only automatic actions (connecting at start, ranging after a D-pad move); manual ranging and the crosshair readout keep working — «Дальность у прицела → не показывать» turns the readout off. Not verified on hardware yet: multi-target mode, writing the gate, the range after a D-pad move.

Not yet implemented end-to-end: MKV recording, encrypted secrets manifest, telemetry in recording metadata, live telemetry polling (PAN/TILT), protocol-level adapters for Relay X3. The UI shows `—` or «не подключено» for these instead of sample values; keep it that way. UI placeholders are not evidence that hardware integration is complete. State this accurately in handoffs.

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
