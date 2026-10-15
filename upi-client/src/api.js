/**
 * Client for the Enterprise Switch (Spring Boot).
 * Every helper returns parsed JSON; non-2xx responses reject with the
 * switch's structured error body ({status, message, ...}) so the UI can
 * branch on the machine-readable `status` code.
 *
 * Endpoints come from build-time env vars so the same source deploys to
 * Vercel unchanged. With no env set (local `npm run dev`) the fallbacks
 * reproduce the original hard-coded localhost behaviour exactly.
 *   VITE_SWITCH_URL  e.g. https://finguard-switch.onrender.com
 *   VITE_ML_URL      e.g. https://finguard-ml.onrender.com
 */

const SWITCH_ORIGIN = (import.meta.env.VITE_SWITCH_URL || 'http://localhost:8081').replace(/\/+$/, '');
const ML_ORIGIN = (import.meta.env.VITE_ML_URL || 'http://localhost:8001').replace(/\/+$/, '');

const SWITCH_BASE = `${SWITCH_ORIGIN}/api/v1/upi`;
const ML_BASE = ML_ORIGIN;

/** Short host:port label for the status bar, so it never lies about where it points. */
function originLabel(origin) {
  try {
    const u = new URL(origin);
    return u.port ? `:${u.port}` : u.host;
  } catch {
    return origin;
  }
}

export const SWITCH_LABEL = originLabel(SWITCH_ORIGIN);
export const ML_LABEL = originLabel(ML_ORIGIN);

async function parseOrThrow(response) {
  const body = await response.json().catch(() => ({
    status: 'NETWORK_ERROR',
    message: 'Unreadable response from switch',
  }));
  if (!response.ok) {
    throw body;
  }
  return body;
}

export async function pay(paymentRequest) {
  let response;
  try {
    response = await fetch(`${SWITCH_BASE}/pay`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(paymentRequest),
    });
  } catch {
    throw {
      status: 'SWITCH_DOWN',
      message: `Cannot reach the banking switch (${SWITCH_ORIGIN})`,
    };
  }
  return parseOrThrow(response);
}

export async function fetchAccount(vpa) {
  const response = await fetch(`${SWITCH_BASE}/account/${encodeURIComponent(vpa)}`);
  return parseOrThrow(response);
}

export async function fetchRecentTransactions() {
  const response = await fetch(`${SWITCH_BASE}/transactions`);
  return parseOrThrow(response);
}

/** Liveness probe against the FastAPI core, for the header status bar. */
export async function fetchMlHealth() {
  const response = await fetch(`${ML_BASE}/health`);
  return parseOrThrow(response);
}
