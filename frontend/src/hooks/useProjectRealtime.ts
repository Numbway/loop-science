import { useEffect, useRef, useState } from "react";
import {
  subscribeProjectRealtime,
  type ProjectRealtimeEvent,
  type RealtimeConnectionState,
} from "../services/realtime";

export function useProjectRealtime(
  projectId: string,
  onEvent: (event: ProjectRealtimeEvent) => void,
): RealtimeConnectionState {
  const callbackRef = useRef(onEvent);
  const [state, setState] = useState<RealtimeConnectionState>(
    projectId ? "connecting" : "offline",
  );

  useEffect(() => {
    callbackRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!projectId) {
      setState("offline");
      return;
    }
    return subscribeProjectRealtime({
      projectId,
      onEvent: (event) => callbackRef.current(event),
      onStateChange: setState,
    });
  }, [projectId]);

  return state;
}
