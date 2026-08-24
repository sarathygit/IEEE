/**
 * Client for the Enterprise Switch (Spring Boot, port 8081).
 * Every helper returns parsed JSON; non-2xx responses reject with the
 * switch's structured error body ({status, message, ...}) so the UI can
 * branch on the machine-readable `status` code.
 */

const SWITCH_BASE = 'http://localhost:8081/api/v1/upi';
const ML_BASE = 'http://localhost:8001';

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
    throw { status: 'SWITCH_DOWN', message: 'Cannot reach the banking switch (is it running on :8081?)' };
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
