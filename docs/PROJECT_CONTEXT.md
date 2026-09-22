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

Implemented as hot-target detection (`desktop/src/alignment.ts`): the brightest compact blob, sub-pixel centroid, error from the first enabled reticle centre in video pixels. Do not fake alignment telemetry when no target is found.

## Recording intent

The operator can record both cameras together or separately, choose directory, layout (separate / split / both), segment duration and an auto-stop timer; MP4 only (MKV is not implemented). A sidecar manifest should include time, camera/device IPs, ONVIF information and TL.0009 telemetry. Credentials are excluded by default. If ever included, they must be encrypted and explicitly enabled.

## TL.0009 rocking test

Up to five profiles are saved. Each profile contains independent PAN/TILT min/max angles and speeds, cycle count, pause and smooth-motion flag. The runtime validates hardware limits, supports immediate cancellation and sends stop to both axes on exit.

## Current state and next steps

The former Python/PyQt client was removed in v0.2.0 (tag `v0.1.0` keeps it in git history). The Tauri client now has live RTSP video, ONVIF zoom/focus, pass-through and split recording with seekable MP4, hot-target alignment measurement and TL.0009 service control. Next vertical slices:

1. rangefinder commands (`desktop/docs/RANGEFINDER_PROTOCOL.md`) and live RANGE in the status bar;
2. Relay X3 channels (`desktop/docs/RELAYX3_PROTOCOL.md`), verified on the device;
3. live PAN/TILT telemetry from TL.0009 into the status bar and recording metadata;
4. verification of split recording and alignment on a real heated target.

## Definition of a portable handoff

A new machine must be able to clone the repository, run `npm ci`, `npm run doctor`, `npm run check` and `npm run dev:native` from `desktop/`. No absolute paths, secrets, generated build trees or machine-local configuration may be required from the originating computer.
