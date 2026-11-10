import { timingSafeEqual } from "node:crypto";
import { dispatch, internalOrigin } from "../server.mjs";

function authorised(req) {
  const expected = process.env.TT_CRON_TOKEN || "";
  const provided = req.headers.get("x-internal-token") || "";
  const a = Buffer.from(expected), b = Buffer.from(provided);
  return expected.length > 0 && a.length === b.length && timingSafeEqual(a, b);
}

export default async function handler(req, context) {
  if (!authorised(req)) return;
  let body;
  try { body = await req.json(); } catch { return; }
  let target;
  if (body.kind === "cron") target = "/api/internal/cron/run";
  else if (body.kind === "backup" && Number.isInteger(body.backup_id) && body.backup_id > 0) target = "/api/internal/backups/run";
  else return;
  const origin = internalOrigin(req, context);
  const internal = new Request(`${origin}${target}`, {
    method: "POST",
    headers: { "X-Internal-Token": process.env.TT_CRON_TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify(body.kind === "backup" ? { backup_id: body.backup_id } : {}),
  });
  const response = await dispatch(internal, context, { timeoutMs: 880000 });
  if (!response.ok) throw new Error("worker_run_failed");
  const result = await response.json();
  if (!result.success) throw new Error("worker_run_failed");
}

export const config = { background: true };
