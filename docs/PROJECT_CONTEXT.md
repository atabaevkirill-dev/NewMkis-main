# ONCAM project context

## What the application is for

The operator observes two simultaneous video channels:

- CAM 01: optical camera whose axis is adjusted;
- CAM 02: thermal camera used as the reference axis.

The primary workflow is to align CAM 01 to CAM 02 and receive an unmistakable visual confirmation after the axes remain within tolerance. The same workstation must configure and test cameras, the TL.0009 platform, rangefinder and Relay X3, and record both channels.

## Target experience

The product should feel like a compact modern cockpit/HUD, not a collection of independent utility windows. Video is always the priority. Advanced controls live in push drawers so opening controls never hides the scene.

The accepted structure is:

```text
global command bar
optional top system drawer
optional CAM 01 drawer | unified dual-video surface | optional CAM 02 drawer
single persistent telemetry/status bar
```

The dual-video surface supports a draggable divider and channel swapping. Video has no permanent technical clutter. Camera OSD is optional. D-pad is hover-only. Zoom uses wheel; focus uses right-button + wheel.

## Alignment behavior

CAM 02 is the reference. The alignment subsystem should eventually calculate `deltaX`, `deltaY` and total pixel error. The default accepted rule is:

- tolerance: 3 px;
- stable duration: 1200 ms;
- confirmation color: white;
- if the error leaves tolerance before the timer finishes, reset the timer.

Both camera calibration and image-registration approach remain implementation work; do not fake live alignment telemetry.

## Recording intent

The operator can record both cameras together or separately, choose directory, MKV/MP4 and segment duration. A sidecar manifest should include time, camera/device IPs, ONVIF information and TL.0009 telemetry. Credentials are excluded by default. If ever included, they must be encrypted and explicitly enabled.

## TL.0009 rocking test

Up to five profiles are saved. Each profile contains independent PAN/TILT min/max angles and speeds, cycle count, pause and smooth-motion flag. The runtime validates hardware limits, supports immediate cancellation and sends stop to both axes on exit.

## Migration strategy

The repository currently contains a mature but tangled Python/PyQt program and a new Tauri client. Migrate by vertical slice:

1. keep the Tauri UI and native config layer buildable;
2. connect real ONVIF lens control;
3. connect both RTSP streams with reconnect/FPS reporting;
4. connect recording and sidecar metadata;
5. add live platform/rangefinder telemetry;
6. implement calibrated axis-alignment measurement;
7. replace remaining Python device adapters only after hardware verification;
8. remove legacy UI only after feature parity.

## Known legacy improvements already present

- hardcoded legacy passwords removed;
- saved legacy config restricted to owner permissions where supported;
- credential-bearing RTSP URLs sanitized in logs;
- Qt dialogs removed from the video worker thread;
- YOLO/torch object detection removed as out of scope for axis alignment;
- camera 2 respects a custom RTSP URL;
- blocking GUI sleep removed;
- missing `psutil` dependency added.

## Definition of a portable handoff

A new machine must be able to clone the repository, run `npm ci`, `npm run doctor`, `npm run check` and `npm run dev:native` from `desktop/`. No absolute paths, secrets, generated build trees or machine-local configuration may be required from the originating computer.
