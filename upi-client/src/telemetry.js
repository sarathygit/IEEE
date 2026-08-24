/**
 * Background device telemetry (architecture step 1).
 *
 * Captured silently alongside the payment inputs and shipped to the switch.
 * Everything here is demo-grade fingerprinting: stable within a browser
 * session, different across devices - enough to exercise the ML features.
 */

/** djb2 over a string, rendered as unsigned hex - tiny stable fingerprint. */
function djb2Hex(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i += 1) {
    h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(16).padStart(8, '0');
}

export function collectTelemetry() {
  const ua = navigator.userAgent || '';

  const deviceType = /android/i.test(ua)
    ? 'Android'
    : /iphone|ipad|ipod/i.test(ua)
      ? 'iOS'
      : 'Web';

  // navigator.connection is Chromium-only; degrade gracefully elsewhere.
  const effective = navigator.connection?.effectiveType || '';
  const networkType =
    effective === '4g' ? '4G'
    : effective === '3g' ? '3G'
    : effective === '5g' ? '5G'
    : 'WiFi';

  const deviceSignature = `dsig-${djb2Hex(
    [ua, screen.width, screen.height, navigator.language].join('|'),
  )}`;

  // Real geolocation needs a permission prompt; the demo hashes the timezone
  // as a coarse, consent-free location proxy.
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'unknown';
  const geoLocationHash = `geo-${djb2Hex(tz)}`;

  return { deviceType, networkType, deviceSignature, geoLocationHash };
}
