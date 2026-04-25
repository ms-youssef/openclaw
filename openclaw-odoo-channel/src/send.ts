/**
 * Outbound message delivery to Odoo.
 * Parses session key to determine where to post, then calls message_post.
 */

import type { ResolvedOdooAccount } from "./accounts.js";
import { OdooClient } from "./odoo-client.js";
import { parseOdooSessionKey } from "./session-key.js";

const clientCache = new Map<string, OdooClient>();

async function getOrCreateClient(account: ResolvedOdooAccount): Promise<OdooClient> {
  const cacheKey = `${account.config.url}:${account.config.login}`;
  let client = clientCache.get(cacheKey);
  if (!client) {
    client = new OdooClient(account.config);
    await client.connect();
    clientCache.set(cacheKey, client);
  }
  return client;
}

/**
 * Send a text message to an Odoo record identified by session key.
 */
export async function sendOdooMessage(params: {
  account: ResolvedOdooAccount;
  sessionKey: string;
  text: string;
  partnerIds?: number[];
}): Promise<{ channel: string; messageId: string; chatId: string }> {
  const parsed = parseOdooSessionKey(params.sessionKey);
  if (!parsed) {
    throw new Error(`Invalid Odoo session key: ${params.sessionKey}`);
  }

  const client = await getOrCreateClient(params.account);

  // Strip thinking blocks from the output boundary before sending to Odoo
  let processedText = params.text;
  processedText = processedText.replace(/<think>[\s\S]*?<\/think>\s*/gi, "");
  processedText = processedText.replace(/<thought>[\s\S]*?<\/thought>\s*/gi, "");
  processedText = processedText.trim();

  const body = processedText.startsWith("<")
    ? processedText
    : `<p>${escapeHtml(processedText)}</p>`;

  await client.postMessage({
    model: parsed.model,
    resId: parsed.resId,
    body,
    partnerIds: params.partnerIds,
  });

  return {
    channel: "odoo",
    messageId: "",
    chatId: `${parsed.model}:${parsed.resId}`,
  };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br/>");
}
