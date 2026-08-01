import type { ExperimentStatus, ExperimentTreeNode } from "./experimentTree";

export type RealtimeConnectionState =
  "connecting" | "live" | "reconnecting" | "offline";

export type ProjectRealtimeEventType =
  | "connected"
  | "heartbeat"
  | "experiment_started"
  | "experiment_progress"
  | "experiment_completed"
  | "experiment_failed"
  | "diagnosis_ready"
  | "new_experiment_created";

export interface ProjectRealtimeEvent {
  event_id: string;
  type: ProjectRealtimeEventType;
  project_id: string;
  occurred_at: string;
  experiment_id?: string;
  status?: ExperimentStatus;
  epoch?: number;
  total_epochs?: number;
  metrics?: Record<string, number>;
  error?: string;
  diagnosis?: string;
  experiment?: ExperimentTreeNode;
  started_at?: string;
  completed_at?: string;
}

interface RealtimeSubscriptionOptions {
  projectId: string;
  onEvent: (event: ProjectRealtimeEvent) => void;
  onStateChange: (state: RealtimeConnectionState) => void;
}

const WS_BASE_URL =
  import.meta.env.VITE_WS_URL || window.location.origin.replace(/^http/, "ws");
const TERMINAL_CLOSE_CODES = new Set([4401, 4403, 4404]);
const RETRY_DELAYS = [1_000, 2_000, 4_000, 8_000, 15_000];

function isRealtimeEvent(value: unknown): value is ProjectRealtimeEvent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ProjectRealtimeEvent>;
  return (
    typeof candidate.event_id === "string" &&
    typeof candidate.type === "string" &&
    typeof candidate.project_id === "string" &&
    typeof candidate.occurred_at === "string"
  );
}

export function subscribeProjectRealtime({
  projectId,
  onEvent,
  onStateChange,
}: RealtimeSubscriptionOptions): () => void {
  let stopped = false;
  let attempt = 0;
  let socket: WebSocket | null = null;
  let retryTimer: number | null = null;

  const clearRetry = () => {
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const scheduleReconnect = () => {
    if (stopped || !navigator.onLine) {
      onStateChange("offline");
      return;
    }
    onStateChange("reconnecting");
    const delay = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
    attempt += 1;
    clearRetry();
    retryTimer = window.setTimeout(connect, delay);
  };

  const connect = () => {
    clearRetry();
    if (stopped || !projectId) return;
    const token = localStorage.getItem("access_token");
    if (!token || !navigator.onLine) {
      onStateChange("offline");
      return;
    }

    onStateChange(attempt > 0 ? "reconnecting" : "connecting");
    const websocketUrl = `${WS_BASE_URL.replace(/\/$/, "")}/ws/projects/${projectId}`;
    socket = new WebSocket(websocketUrl, ["bearer", token]);

    socket.onopen = () => {
      attempt = 0;
      onStateChange("live");
    };
    socket.onmessage = (message) => {
      try {
        const event: unknown = JSON.parse(String(message.data));
        if (isRealtimeEvent(event) && event.project_id === projectId) {
          onEvent(event);
        }
      } catch {
        // Ignore malformed frames while keeping the subscription alive.
      }
    };
    socket.onerror = () => socket?.close();
    socket.onclose = (event) => {
      socket = null;
      if (stopped) return;
      if (TERMINAL_CLOSE_CODES.has(event.code)) {
        onStateChange("offline");
        return;
      }
      scheduleReconnect();
    };
  };

  const handleOnline = () => {
    if (stopped || socket) return;
    attempt = 0;
    connect();
  };
  const handleOffline = () => {
    clearRetry();
    onStateChange("offline");
    socket?.close();
  };

  window.addEventListener("online", handleOnline);
  window.addEventListener("offline", handleOffline);
  connect();

  return () => {
    stopped = true;
    clearRetry();
    window.removeEventListener("online", handleOnline);
    window.removeEventListener("offline", handleOffline);
    if (socket && socket.readyState < WebSocket.CLOSING) {
      socket.close(1000, "View closed");
    }
    socket = null;
  };
}
