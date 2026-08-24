import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { pay, fetchAccount, fetchRecentTransactions, fetchMlHealth } from './api.js';
import { collectTelemetry } from './telemetry.js';

/**
 * FinGuard-AI :: Module 4 - RT-IIPF Core Switch Monitor.
 *
 * Internal enterprise dashboard skin over the same backend wiring:
 *   - left panel : payment injection console (POST /api/v1/upi/pay)
 *   - right panel: raw audit log viewport streaming transaction_logs
 *   - header     : live service status polled from both backends
 */

const DEMO_ACCOUNTS = [
  { vpa: 'arjun@fgbank', name: 'Arjun Mehta', hint: '4321' },
  { vpa: 'priya@fgbank', name: 'Priya Nair', hint: '9876' },
  { vpa: 'ravi@fgbank', name: 'Ravi Kumar', hint: '2468' },
];

const TRANSACTION_TYPES = ['P2P', 'P2M', 'Bill Payment', 'Recharge'];
const MERCHANT_CATEGORIES = [
  'Grocery', 'Food', 'Shopping', 'Entertainment', 'Fuel',
  'Transport', 'Utilities', 'Healthcare', 'Education', 'Other',
];

const POLL_MS = 4000;

/* ---------- raw log-line formatting ---------- */

function pad(n) { return String(n).padStart(2, '0'); }

function formatTs(isoString) {
  const d = new Date(isoString);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function shortRef(txnRef) {
  return `${txnRef.slice(2, 6)}-${txnRef.slice(-2)}`.toLowerCase();
}

function shortVpa(vpa) {
  return `${vpa.split('@')[0]}@fg`;
}

function formatInr(amount) {
  return `₹${Number(amount).toLocaleString('en-IN')}`;
}

export default function App() {
  const [payerVpa, setPayerVpa] = useState(DEMO_ACCOUNTS[0].vpa);
  const [payeeVpa, setPayeeVpa] = useState('grocery@fgpay');
  const [amount, setAmount] = useState('');
  const [mpin, setMpin] = useState('');
  const [txnType, setTxnType] = useState('P2M');
  const [category, setCategory] = useState('Grocery');
  const [account, setAccount] = useState(null);
  const [feed, setFeed] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mlUp, setMlUp] = useState(false);
  const [switchUp, setSwitchUp] = useState(false);

  const telemetry = useMemo(() => collectTelemetry(), []);
  const terminalRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [acct, txns] = await Promise.all([
        fetchAccount(payerVpa),
        fetchRecentTransactions(),
      ]);
      setAccount(acct);
      setFeed(txns);
      setSwitchUp(true);
    } catch {
      setAccount(null);
      setSwitchUp(false);
    }
    try {
      await fetchMlHealth();
      setMlUp(true);
    } catch {
      setMlUp(false);
    }
  }, [payerVpa]);

  // Live monitor semantics: poll both services so the header status and the
  // audit stream track backend reality without manual reloads.
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  // Keep the terminal pinned to the newest line, like tail -f.
  useEffect(() => {
    const el = terminalRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [feed]);

  async function submitPayment(event) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const response = await pay({
        payerVpa,
        payeeVpa: payeeVpa.trim(),
        amountInr: Number(amount),
        mpin,
        transactionType: txnType,
        merchantCategory: category,
        ...telemetry,
      });
      setResult({ kind: 'COMMIT', ...response });
    } catch (err) {
      setResult({
        kind: err.status === 'BLOCKED_FRAUD' ? 'BLOCKED' : 'REJECTED',
        ...err,
      });
    } finally {
      setBusy(false);
      setMpin('');
      refresh();
    }
  }

  // Chronological order (oldest first) - raw logs append at the bottom.
  const logLines = [...feed].reverse();

  return (
    <div className="console">
      {/* ---------- global status bar ---------- */}
      <header className="statusbar">
        <span className="statusbar-brand">RT-IIPF // CORE SWITCH MONITOR</span>
        <span className="statusbar-sep">|</span>
        <span className={mlUp ? 'svc up' : 'svc down'}>
          <i className="dot" /> FASTAPI CORE: {mlUp ? 'CONNECTED' : 'OFFLINE'} (:8001)
        </span>
        <span className="statusbar-sep">|</span>
        <span className={switchUp ? 'svc up' : 'svc down'}>
          <i className="dot" /> H2 ENGINE: {switchUp ? 'ACTIVE' : 'UNREACHABLE'} (:8081)
        </span>
        <span className="statusbar-fill" />
        <span className="statusbar-meta">
          TELEMETRY {telemetry.deviceType.toUpperCase()}/{telemetry.networkType} · {telemetry.deviceSignature}
        </span>
      </header>

      <div className="grid">
        {/* ---------- left: payment injection console ---------- */}
        <section className="panel form-panel">
          <div className="panel-title">UPI PAYMENT CONSOLE // SECURE ENTRY</div>

          <form onSubmit={submitPayment} className="pay-form">
            <label className="field">
              <span className="field-label">ORIGIN ACCOUNT</span>
              <select value={payerVpa} onChange={(e) => setPayerVpa(e.target.value)}>
                {DEMO_ACCOUNTS.map((a) => (
                  <option key={a.vpa} value={a.vpa}>{a.vpa} — {a.name}</option>
                ))}
              </select>
            </label>

            <div className={`acct-strip ${account?.accountLocked ? 'locked' : ''}`}>
              {account
                ? account.accountLocked
                  ? `ACCT STATUS: LOCKED_BY_SECURITY // TRANSACTIONS SUSPENDED`
                  : `AVAIL BAL: ${formatInr(account.balanceInr)}  |  BANK: ${account.bank.toUpperCase()}  |  STATUS: UNLOCKED`
                : 'ACCT STATUS: SWITCH UNREACHABLE'}
            </div>

            <label className="field">
              <span className="field-label">DESTINATION VPA</span>
              <input
                value={payeeVpa}
                onChange={(e) => setPayeeVpa(e.target.value)}
                placeholder="name@bank"
                required
                spellCheck="false"
              />
            </label>

            <label className="field">
              <span className="field-label">AMOUNT (INR)</span>
              <input
                type="number"
                min="1"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                required
              />
            </label>

            <div className="field-row">
              <label className="field">
                <span className="field-label">TXN TYPE</span>
                <select value={txnType} onChange={(e) => setTxnType(e.target.value)}>
                  {TRANSACTION_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field-label">MCC CATEGORY</span>
                <select value={category} onChange={(e) => setCategory(e.target.value)}>
                  {MERCHANT_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                </select>
              </label>
            </div>

            <label className="field">
              <span className="field-label">
                MPIN <span className="field-hint">[demo: {DEMO_ACCOUNTS.find((a) => a.vpa === payerVpa)?.hint}]</span>
              </span>
              <input
                type="password"
                inputMode="numeric"
                pattern="\d{4,6}"
                maxLength={6}
                value={mpin}
                onChange={(e) => setMpin(e.target.value.replace(/\D/g, ''))}
                placeholder="****"
                required
              />
            </label>

            <button className="exec-btn" type="submit" disabled={busy || account?.accountLocked}>
              {busy ? '>> SCORING INLINE — THREAD HELD <<' : 'EXECUTE PAYMENT'}
            </button>
          </form>

          {/* ---------- verdict readout ---------- */}
          {result && result.kind === 'COMMIT' && (
            <div className="verdict commit">
              <div className="verdict-tag">[ COMMIT ]</div>
              <pre>{[
                `TXN      : ${result.txnRef}`,
                `ROUTE    : ${payerVpa} -> ${result.payeeVpa}`,
                `AMT      : ${formatInr(result.amountInr)}`,
                `SCORE    : ${result.anomalyScore?.toFixed(3)}  (threshold 0.850)`,
                `LATENCY  : ${result.processingMs}ms end-to-end`,
                `NEW BAL  : ${formatInr(result.remainingBalance)}`,
                `LEDGER   : COMMITTED`,
              ].join('\n')}</pre>
            </div>
          )}

          {result && result.kind === 'BLOCKED' && (
            <div className="verdict blocked">
              <div className="verdict-tag">[ CRITICAL_ALERT ]</div>
              <pre>{[
                `TXN      : ${result.txnRef}`,
                `SCORE    : ${result.anomalyScore?.toFixed(3)}  >=  threshold 0.850`,
                `ACTION   : ROLLBACK EXECUTED — NO FUNDS MOVED`,
                `ACCOUNT  : ROW LOCKED (${payerVpa})`,
                `MSG      : ${result.message}`,
              ].join('\n')}</pre>
            </div>
          )}

          {result && result.kind === 'REJECTED' && (
            <div className="verdict rejected">
              <div className="verdict-tag">[ REJECTED ]</div>
              <pre>{[
                `CODE     : ${result.status}`,
                `MSG      : ${result.message}`,
                `LEDGER   : UNTOUCHED`,
              ].join('\n')}</pre>
            </div>
          )}
        </section>

        {/* ---------- right: raw audit log viewport ---------- */}
        <section className="terminal-panel">
          <div className="terminal-titlebar">
            root@finguard-switch:~# tail -f /var/log/finguard/transaction_audit.log
          </div>
          <div className="terminal" ref={terminalRef}>
            <div className="log-line boot">FinGuard-AI switch audit stream attached — polling H2 transaction_logs every {POLL_MS / 1000}s</div>
            {logLines.length === 0 && (
              <div className="log-line idle">-- no transaction events; stream idle --</div>
            )}
            {logLines.map((t) => {
              const blocked = t.status !== 'SUCCESS';
              return (
                <div key={t.txnRef} className="log-line">
                  <span className="ts">{formatTs(t.createdAt)} </span>
                  <span className={blocked ? 'tag crit' : 'tag ok'}>
                    {blocked ? '[ CRITICAL_ALERT ]' : '[ OK ]'}
                  </span>
                  <span className="body">
                    {' '}TXN: {shortRef(t.txnRef)} | {shortVpa(t.senderVpa)} -&gt; {shortVpa(t.receiverVpa)} | AMT: {formatInr(t.amountInr)} | SCORE: {t.anomalyScore.toFixed(3)} | LATENCY: {t.processingMs}ms
                  </span>
                  {blocked && <span className="rollback"> -&gt; ROLLBACK EXECUTED</span>}
                </div>
              );
            })}
            <div className="log-line cursor-line"><span className="cursor">█</span></div>
          </div>
        </section>
      </div>
    </div>
  );
}
