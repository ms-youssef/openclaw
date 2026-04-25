import type { OdooSessionKeyParts } from "./types.js";

/**
 * Build an Odoo session key from components.
 * Format: odoo:<hostname>:<model>:<res_id>
 */
export function buildOdooSessionKey(hostname: string, model: string, resId: number | string): string {
  return `odoo:${hostname}:${model}:${resId}`;
}

/**
 * Parse an Odoo session key into components.
 * Returns null if the key doesn't match the expected format.
 */
export function parseOdooSessionKey(sessionKey: string): OdooSessionKeyParts | null {
  const parts = sessionKey.split(":");
  if (parts.length < 4 || parts[0] !== "odoo") {
    return null;
  }
  const hostname = parts[1];
  const resId = parseInt(parts[parts.length - 1], 10);
  if (isNaN(resId)) {
    return null;
  }
  const model = parts.slice(2, parts.length - 1).join(":");
  return { hostname, model, resId };
}

/**
 * Extract the hostname from an Odoo URL.
 */
export function extractHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}
