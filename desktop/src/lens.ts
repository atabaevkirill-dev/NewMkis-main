import { cameraLensStep } from "./api";
import type { CameraConfig } from "./types";

export type LensMode = "zoom" | "focus";

/** Must match `MAX_STEPS` in onvif.rs. */
const MAX_STEPS = 10;

interface Queue {
  camera: CameraConfig;
  busy: boolean;
  pending: Record<LensMode, number>;
  onError: (error: unknown) => void;
}

const queues = new Map<CameraConfig["id"], Queue>();

/**
 * One lens step (wheel notch or button press). An idle camera gets it at once; steps arriving while
 * a command runs are merged into the next one, so fast scrolling never leaves a backlog that keeps
 * the lens moving after the wheel has stopped. Opposite steps cancel out.
 */
export function lensStep(camera: CameraConfig, mode: LensMode, direction: 1 | -1, onError: (error: unknown) => void): void {
  const queue = queues.get(camera.id) ?? { camera, busy: false, pending: { zoom: 0, focus: 0 }, onError };
  queues.set(camera.id, queue);
  queue.camera = camera;
  queue.onError = onError;
  queue.pending[mode] = Math.max(-MAX_STEPS, Math.min(MAX_STEPS, queue.pending[mode] + direction));
  if (!queue.busy) void pump(queue);
}

async function pump(queue: Queue): Promise<void> {
  queue.busy = true;
  try {
    for (;;) {
      const mode: LensMode | null = queue.pending.zoom !== 0 ? "zoom" : queue.pending.focus !== 0 ? "focus" : null;
      if (!mode) return;
      const steps = queue.pending[mode];
      queue.pending[mode] = 0;
      try {
        await cameraLensStep(queue.camera, mode, steps);
      } catch (error) {
        // Whatever queued behind a failed command would fail the same way.
        queue.pending = { zoom: 0, focus: 0 };
        queue.onError(error);
        return;
      }
    }
  } finally {
    queue.busy = false;
  }
}
