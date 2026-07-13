// Thin fetch wrappers around the backend API.
async function jget(path) {
  const r = await fetch(path);
  return r.json();
}
async function jpost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

export const api = {
  health: () => jget("/api/health"),
  chat: (sessionId, message) => jpost("/api/chat", { sessionId, message }),
  sessions: () => jget("/api/sessions"),
  transcript: (id) => jget("/api/sessions/" + encodeURIComponent(id)),
  evalRuns: () => jget("/api/eval/runs"),
  evalRun: (id) => jget("/api/eval/runs/" + encodeURIComponent(id)),
  metricsFiles: () => jget("/api/metrics/files"),
  metricsFile: (name) => jget("/api/metrics/files/" + encodeURIComponent(name)),
  truth: (kind) => jget("/api/truth/" + encodeURIComponent(kind)),
  message: (id) => jget("/api/truth/message/" + encodeURIComponent(id)),
};
