/**
 * Odoo Discuss channel plugin for OpenClaw.
 *
 * Connects to Odoo's messaging system (Discuss channels, task chatter, etc.)
 * via WebSocket bus for real-time notifications and JSON-RPC for posting.
 */

import type { ChannelPlugin } from "openclaw/plugin-sdk/compat";
import { createScopedChannelConfigBase } from "openclaw/plugin-sdk/compat";
import {
  resolveOdooAccount,
  listOdooAccountIds,
  resolveDefaultOdooAccountId,
  type ResolvedOdooAccount,
} from "./accounts.js";
import { getOdooRuntime } from "./runtime.js";
import { parseOdooSessionKey } from "./session-key.js";

const odooConfigBase = createScopedChannelConfigBase<ResolvedOdooAccount>({
  sectionKey: "odoo",
  listAccountIds: listOdooAccountIds,
  resolveAccount: (cfg: any, accountId: string) => resolveOdooAccount({ cfg, accountId }),
  defaultAccountId: resolveDefaultOdooAccountId,
  clearBaseFields: ["url", "db", "login", "password"],
});

export const odooPlugin: ChannelPlugin<ResolvedOdooAccount> = {
  id: "odoo",
  meta: {
    displayName: "Odoo Discuss",
    description: "Connect to Odoo Discuss channels and document chatter",
  },
  capabilities: {
    chatTypes: ["direct", "group"],
    reactions: false,
    threads: false,
    media: false,
    nativeCommands: false,
    blockStreaming: true,
  },
  streaming: {
    blockStreamingCoalesceDefaults: { minChars: 500, idleMs: 2000 },
  },
  reload: { configPrefixes: ["channels.odoo"] },
  config: {
    ...odooConfigBase,
    isConfigured: (account: ResolvedOdooAccount) => account.configured,
    describeAccount: (account: ResolvedOdooAccount) => ({
      accountId: account.accountId,
      name: account.name,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
  security: {
    resolveDmPolicy: () => ({ policy: "open" }),
  },
  messaging: {
    normalizeTarget: (raw: string) => raw?.trim() ?? null,
    targetResolver: {
      looksLikeId: (raw: string) => {
        const trimmed = raw.trim();
        return /^odoo:.+:\d+$/.test(trimmed) || /^[\w.]+:\d+$/.test(trimmed);
      },
      hint: "<model:res_id> or <odoo:host:model:res_id>",
    },
  },
  outbound: {
    deliveryMode: "direct",
    chunker: (text: string, limit: number) => getOdooRuntime().channel.text.chunkMarkdownText(text, limit),
    chunkerMode: "markdown",
    textChunkLimit: 10_000,
    resolveTarget: ({ to }: { to?: string }) => {
      const trimmed = to?.trim() ?? "";
      if (!trimmed) {
        return { ok: false, error: "Odoo target required (e.g. discuss.channel:8 or project.task:42)" };
      }
      const parsed = parseOdooSessionKey(trimmed);
      if (parsed) {
        return { ok: true, to: trimmed };
      }
      const match = trimmed.match(/^([\w.]+):(\d+)$/);
      if (match) {
        return { ok: true, to: trimmed };
      }
      return { ok: false, error: `Invalid Odoo target: ${trimmed}` };
    },
    sendText: async ({ cfg, to, text, accountId }: { cfg: any; to: string; text: string; accountId?: string }) => {
      const account = resolveOdooAccount({ cfg, accountId });
      const { sendOdooMessage } = await import("./send.js");
      return await sendOdooMessage({
        account,
        sessionKey: to,
        text,
      });
    },
  },
  gateway: {
    startAccount: async (ctx: any) => {
      const account = ctx.account;
      ctx.log?.info(`[odoo:${account.accountId}] starting Odoo monitor`);

      const { startOdooMonitor } = await import("./monitor.js");
      await startOdooMonitor({
        account,
        config: ctx.cfg,
        abortSignal: ctx.abortSignal,
        log: (...args: any[]) => ctx.log?.info(...args),
        error: (...args: any[]) => ctx.log?.error(...args),
      });
    },
  },
};
