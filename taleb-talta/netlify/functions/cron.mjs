/* Scheduled every minute; hands work to the 15-minute background runtime. */
export default async function handler(req, context) {
  const origin = (process.env.TT_PUBLIC_ORIGIN || context?.site?.url || "").replace(/\/$/, "");
  const token = process.env.TT_CRON_TOKEN;
  if (!origin || !token) throw new Error("cron_configuration_missing");
  const response = await fetch(`${origin}/.netlify/functions/worker-background`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Internal-Token": token },
    body: JSON.stringify({ kind: "cron" }),
    signal: AbortSignal.timeout(20000),
  });
  if (![200, 202].includes(response.status)) throw new Error("cron_schedule_failed");
  return new Response("scheduled", { status: 200 });
}

export const config = { schedule: "* * * * *" };
