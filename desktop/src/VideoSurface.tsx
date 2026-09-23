import { memo, useEffect, useRef, useState } from "react";
import { COARSE_WIDTH, findBlob, refineCentroid, type TargetFix } from "./alignment";
import { diagLog, inTauri, startCameraStream } from "./api";
import { OFF_STATS } from "./config";
import type { CameraConfig, StreamEvent, VideoStats } from "./types";

/**
 * Frames waiting in the decoder beyond this (~2 s) mean it truly cannot keep up: only then drop to the
 * next key frame. A small limit froze the picture for a whole GOP whenever fast platform motion made
 * the frames briefly larger than the decoder could absorb.
 */
const MAX_DECODE_QUEUE = 60;
const STATS_MS = 1000;
const MEASURE_MS = 200;

/**
 * Renders one camera stream. Encoded H.264/H.265 frames arrive from the native RTSP client and are
 * decoded by WebCodecs (hardware decoder when available) straight onto the canvas.
 */
export const VideoSurface = memo(function VideoSurface({ camera, active, restartKey, onStats, measure, onTarget }: {
  camera: CameraConfig;
  active: boolean;
  /** Changing it reopens the stream, e.g. after the password was changed. */
  restartKey: number;
  onStats: (id: CameraConfig["id"], stats: VideoStats) => void;
  /** Search the frames for the hot alignment target. */
  measure: boolean;
  onTarget: (id: CameraConfig["id"], fix: TargetFix | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const onStatsRef = useRef(onStats);
  onStatsRef.current = onStats;
  const onTargetRef = useRef(onTarget);
  onTargetRef.current = onTarget;
  const [marker, setMarker] = useState<{ left: number; top: number } | null>(null);
  const { id, ip, rtspPort, onvifPort, username, streamPath, streamAuto } = camera;

  // Alignment: ~5 times a second find the hot target and report its sub-pixel position.
  useEffect(() => {
    const canvas = canvasRef.current;
    const report = (fix: TargetFix | null) => {
      onTargetRef.current(id, fix);
      if (!fix || !canvas) return setMarker(null);
      const rect = canvas.getBoundingClientRect();
      setMarker({ left: rect.width / 2 + (fix.x - fix.width / 2) * fix.scale, top: rect.height / 2 + (fix.y - fix.height / 2) * fix.scale });
    };
    if (!measure || !active || !canvas) {
      report(null);
      return;
    }
    const coarse = document.createElement("canvas");
    const coarseContext = coarse.getContext("2d", { willReadFrequently: true });
    const context = canvas.getContext("2d");
    const timer = window.setInterval(() => {
      const { width, height } = canvas;
      const rect = canvas.getBoundingClientRect();
      if (!coarseContext || !context || width < 16 || height < 16 || rect.width === 0) return report(null);
      coarse.width = COARSE_WIDTH;
      coarse.height = Math.max(1, Math.round((COARSE_WIDTH * height) / width));
      coarseContext.drawImage(canvas, 0, 0, coarse.width, coarse.height);
      const blob = findBlob(coarseContext.getImageData(0, 0, coarse.width, coarse.height));
      if (!blob) return report(null);
      const factor = width / coarse.width;
      const x0 = Math.max(0, Math.floor((blob.x0 - 1) * factor));
      const y0 = Math.max(0, Math.floor((blob.y0 - 1) * factor));
      const x1 = Math.min(width, Math.ceil((blob.x1 + 2) * factor));
      const y1 = Math.min(height, Math.ceil((blob.y1 + 2) * factor));
      const centroid = refineCentroid(context.getImageData(x0, y0, x1 - x0, y1 - y0), blob.threshold);
      if (!centroid) return report(null);
      report({ x: x0 + centroid.x, y: y0 + centroid.y, width, height, scale: Math.min(rect.width / width, rect.height / height) });
    }, MEASURE_MS);
    return () => {
      window.clearInterval(timer);
      report(null);
    };
  }, [measure, active, id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    const report = (stats: VideoStats) => onStatsRef.current(id, stats);
    if (!active || !canvas || !context || !inTauri()) {
      // Only a stream that is switched off clears the picture; a restart keeps the last frame visible.
      if (canvas && context) context.clearRect(0, 0, canvas.width, canvas.height);
      report(OFF_STATS);
      return;
    }
    if (typeof VideoDecoder === "undefined") {
      report({ ...OFF_STATS, state: "error", message: "WebCodecs недоступен в этом WebView" });
      return;
    }

    let disposed = false;
    let decoder: VideoDecoder | null = null;
    let needKey = true;
    let drawn = 0;
    /** Frames skipped while waiting for a key frame (overload, decoder error); shown to the operator. */
    let dropped = 0;
    // Timing diagnostics, logged every 5 s: gaps between arriving frames and between drawn frames.
    let lastArrival = 0, maxArrivalGap = 0, lastDraw = 0, maxDrawGap = 0, maxQueue = 0, diagAt = performance.now();
    let submitted = 0, output = 0, maxHeld = 0, loggedDropped = 0;
    // Only anomalies are logged: a draw pause over 150 ms or newly dropped frames.
    let stats: VideoStats = { ...OFF_STATS, state: "connecting" };
    const update = (patch: Partial<VideoStats>) => {
      stats = { ...stats, ...patch };
      report(stats);
    };

    const closeDecoder = () => {
      if (decoder && decoder.state !== "closed") decoder.close();
      decoder = null;
    };

    type ConfigEvent = Extract<StreamEvent, { kind: "config" }>;
    let lastConfig: ConfigEvent | null = null;
    let configuring = false;

    const configure = (event: ConfigEvent) => {
      closeDecoder();
      lastConfig = event;
      configuring = true;
      submitted = output = 0;
      needKey = true;
      const config: VideoDecoderConfig = {
        codec: event.codec,
        codedWidth: event.codedWidth,
        codedHeight: event.codedHeight,
        description: event.description,
        optimizeForLatency: true,
        // The hardware (D3D11) decoder held frames back in bursts of 5–6 (150–240 ms stalls at rest);
        // 720p/640×512 software decoding is cheap and outputs every frame as soon as it is decoded.
        hardwareAcceleration: "prefer-software",
      };
      update({ width: event.width, height: event.height });
      VideoDecoder.isConfigSupported(config)
        .then((support) => {
          if (disposed || lastConfig !== event) return;
          configuring = false;
          if (!support.supported) {
            lastConfig = null;
            update({ state: "error", message: `Кодек ${event.codec} не поддерживается декодером (для H.265 переключите камеру на H.264)` });
            return;
          }
          const next = new VideoDecoder({
            output: (frame) => {
              if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
                canvas.width = frame.displayWidth;
                canvas.height = frame.displayHeight;
              }
              context.drawImage(frame, 0, 0);
              frame.close();
              drawn += 1;
              output += 1;
              const drawnAt = performance.now();
              if (lastDraw) maxDrawGap = Math.max(maxDrawGap, drawnAt - lastDraw);
              lastDraw = drawnAt;
            },
            error: (error) => {
              if (disposed || decoder !== next) return;
              // A corrupt frame closes the decoder; it is rebuilt from the last config at the next key frame.
              update({ message: `Декодер: ${error.message}` });
              decoder = null;
            },
          });
          next.configure(config);
          decoder = next;
        })
        .catch((error) => {
          if (disposed) return;
          configuring = false;
          update({ state: "error", message: `Декодер: ${String(error)}` });
        });
    };

    const decode = (event: Extract<StreamEvent, { kind: "frame" }>) => {
      const arrivedAt = performance.now();
      if (lastArrival) maxArrivalGap = Math.max(maxArrivalGap, arrivedAt - lastArrival);
      lastArrival = arrivedAt;
      if (decoder) maxQueue = Math.max(maxQueue, decoder.decodeQueueSize);
      if (!decoder && !configuring && lastConfig && event.key) configure(lastConfig);
      if (!decoder || decoder.state !== "configured") return;
      if (decoder.decodeQueueSize > MAX_DECODE_QUEUE) needKey = true;
      if (needKey && !event.key) {
        dropped += 1;
        return;
      }
      needKey = false;
      decoder.decode(new EncodedVideoChunk({ type: event.key ? "key" : "delta", timestamp: event.timestamp, data: event.data }));
      submitted += 1;
      maxHeld = Math.max(maxHeld, submitted - output);
    };

    const stream = startCameraStream(camera, (event) => {
      if (disposed) return;
      if (event.kind === "frame") decode(event);
      else if (event.kind === "config") configure(event);
      else if (event.state === "connecting") {
        // A reconnect is not a stutter: timing diagnostics start over with the new session.
        lastArrival = lastDraw = 0;
        // The message says where the stream is being looked for (e.g. the path found over ONVIF).
        update({ state: "connecting", fps: null, message: event.message });
      }
      else if (event.state === "playing") update({ state: "playing", message: event.message });
      else {
        closeDecoder();
        update({ state: "error", fps: null, message: event.message });
      }
    });
    stream.started.catch((error) => !disposed && update({ state: "error", message: String(error) }));
    report(stats);

    let lastTick = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const fps = (drawn * 1000) / (now - lastTick);
      drawn = 0;
      lastTick = now;
      if (stats.state === "playing") update({ fps: Math.round(fps * 10) / 10, dropped });
      if (stats.state === "playing" && now - diagAt >= 5000 && maxDrawGap < 150 && dropped === loggedDropped) {
        maxArrivalGap = maxDrawGap = maxQueue = maxHeld = 0;
        diagAt = now;
      } else if (stats.state === "playing" && now - diagAt >= 5000) {
        loggedDropped = dropped;
        diagLog(`окно ${ip}: макс. пауза прихода ${Math.round(maxArrivalGap)} мс, макс. пауза отрисовки ${Math.round(maxDrawGap)} мс, макс. очередь декодера ${maxQueue}, декодер держит до ${maxHeld} кадров, пропущено ${dropped}`);
        maxArrivalGap = maxDrawGap = maxQueue = maxHeld = 0;
        diagAt = now;
      }
    }, STATS_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
      stream.stop();
      closeDecoder();
      report(OFF_STATS);
    };
    // Only the connection fields reopen the stream; reticle or OSD edits must not.
  }, [active, restartKey, id, ip, rtspPort, onvifPort, username, streamPath, streamAuto]);

  return (
    <>
      <canvas ref={canvasRef} className="video-canvas" data-camera={id} />
      {marker && <i className="target-marker" style={{ left: marker.left, top: marker.top }} title="Найденная мишень" />}
    </>
  );
});
