/**
 * Inbound message monitor for Odoo.
 *
 * Connects to Odoo's WebSocket bus for real-time notifications
 * and polls as a fallback. Dispatches messages to the OpenClaw agent.
 */

import type { ResolvedOdooAccount } from "./accounts.js";
import { OdooClient, type FormattedOdooMessage } from "./odoo-client.js";
import { getOdooRuntime } from "./runtime.js";

type OpenClawConfig = { channels?: Record<string, any>; [key: string]: any };

export type OdooMonitorOptions = {
  account: ResolvedOdooAccount;
  config: OpenClawConfig;
  abortSignal?: AbortSignal;
  log?: (...args: any[]) => void;
  error?: (...args: any[]) => void;
};

const MAX_DEDUP_SIZE = 10_000;

export async function startOdooMonitor(options: OdooMonitorOptions): Promise<void> {
  const { account, config, abortSignal, log, error } = options;
  const reconnectDelay = (account.config.reconnectDelay ?? 5) * 1000;
  const pollInterval = (account.config.pollInterval ?? 15) * 1000;

  const processedMessageIds = new Set<number>();
  const processedOrder: number[] = [];

  function trackProcessed(msgId: number) {
    if (processedMessageIds.has(msgId)) return;
    processedMessageIds.add(msgId);
    processedOrder.push(msgId);
    while (processedOrder.length > MAX_DEDUP_SIZE) {
      const oldest = processedOrder.shift()!;
      processedMessageIds.delete(oldest);
    }
  }

  while (!abortSignal?.aborted) {
    const client = new OdooClient(account.config);
    try {
      await client.connect();
      log?.(`[odoo:${account.accountId}] authenticated as partner_id=${client.partnerIdValue}`);

      await catchUp(client, account, processedMessageIds, trackProcessed, config, log, error);

      log?.(`[odoo:${account.accountId}] starting WebSocket + polling listeners`);
      await Promise.race([
        listenWebSocket(client, account, processedMessageIds, trackProcessed, config, abortSignal, log, error),
        pollLoop(client, account, processedMessageIds, trackProcessed, config, pollInterval, abortSignal, log, error),
      ]);
    } catch (err) {
      error?.(`[odoo:${account.accountId}] connection error: ${err}`);
    }

    if (abortSignal?.aborted) break;
    log?.(`[odoo:${account.accountId}] reconnecting in ${reconnectDelay / 1000}s...`);
    await sleep(reconnectDelay);
  }
}

async function catchUp(
  client: OdooClient,
  account: ResolvedOdooAccount,
  processedIds: Set<number>,
  track: (id: number) => void,
  config: OpenClawConfig,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  log?.(`[odoo:${account.accountId}] catching up on unread notifications...`);
  try {
    const { messages, notifIds } = await client.getUnreadNotifications();
    log?.(`[odoo:${account.accountId}] found ${messages.length} unread messages, ${notifIds.length} notifications`);

    for (const msg of messages) {
      if (processedIds.has(msg.id)) continue;
      if (Array.isArray(msg.author_id) && msg.author_id[0] === client.partnerIdValue) continue;

      const formatted = client.formatMessage(msg);
      if (formatted) {
        log?.(`[odoo:${account.accountId}] catch-up message: ${formatted.sessionKey} from ${formatted.senderName}`);
        await dispatchToAgent(formatted, account, config, log, error);
        track(msg.id);
      }
    }

    await client.markNotificationsRead(notifIds);
    log?.(`[odoo:${account.accountId}] caught up on ${messages.length} messages`);
  } catch (err) {
    error?.(`[odoo:${account.accountId}] catch-up error: ${err}`);
  }
}

async function listenWebSocket(
  client: OdooClient,
  account: ResolvedOdooAccount,
  processedIds: Set<number>,
  track: (id: number) => void,
  config: OpenClawConfig,
  abortSignal?: AbortSignal,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  log?.(`[odoo:${account.accountId}] connecting WebSocket...`);
  return new Promise<void>((resolve, reject) => {
    client.listenBus({
      signal: abortSignal,
      onNotifications: (notifications) => {
        log?.(`[odoo:${account.accountId}] WS: received ${notifications.length} bus notifications`);
        for (const notif of notifications) {
          void processNotification(notif, client, account, processedIds, track, config, log, error).catch(
            (err) => error?.(`[odoo:${account.accountId}] notification processing error: ${err}`),
          );
        }
      },
      onError: (err) => {
        error?.(`[odoo:${account.accountId}] WebSocket error: ${err.message}`);
        reject(err);
      },
      onClose: () => {
        log?.(`[odoo:${account.accountId}] WebSocket closed`);
        resolve();
      },
    });
  });
}

async function pollLoop(
  client: OdooClient,
  account: ResolvedOdooAccount,
  processedIds: Set<number>,
  track: (id: number) => void,
  config: OpenClawConfig,
  interval: number,
  abortSignal?: AbortSignal,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  log?.(`[odoo:${account.accountId}] poll loop started (interval=${interval/1000}s)`);
  while (!abortSignal?.aborted) {
    await sleep(interval);
    if (abortSignal?.aborted) break;

    try {
      const { messages, notifIds } = await client.getUnreadNotifications();
      if (messages.length > 0) {
        log?.(`[odoo:${account.accountId}] poll: found ${messages.length} unread messages`);
      }
      for (const msg of messages) {
        if (processedIds.has(msg.id)) continue;
        if (Array.isArray(msg.author_id) && msg.author_id[0] === client.partnerIdValue) continue;

        const formatted = client.formatMessage(msg);
        if (formatted) {
          log?.(`[odoo:${account.accountId}] poll message: ${formatted.sessionKey} from ${formatted.senderName}`);
          await dispatchToAgent(formatted, account, config, log, error);
          track(msg.id);
        }
      }
      if (notifIds.length > 0) {
        await client.markNotificationsRead(notifIds);
      }
    } catch (err) {
      error?.(`[odoo:${account.accountId}] poll error: ${err}`);
    }
  }
}

async function processNotification(
  notif: any,
  client: OdooClient,
  account: ResolvedOdooAccount,
  processedIds: Set<number>,
  track: (id: number) => void,
  config: OpenClawConfig,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  const msg = notif.message ?? notif;
  const type = msg.type;

  if (type === "discuss.channel/new_message") {
    log?.(`[odoo:${account.accountId}] new_message payload: ${JSON.stringify(msg.payload).slice(0, 500)}`);
    await processNewMessage(msg.payload, client, account, processedIds, track, config, log, error);
    return;
  }

  if (type !== "mail.record/insert") return;

  const payload = msg.payload;
  log?.(`[odoo:${account.accountId}] mail.record/insert full msg: ${JSON.stringify(msg).slice(0, 500)}`);
  if (!payload) return;

  const messageRecords = payload.Message ?? payload["mail.message"] ?? payload.mail_message ?? [];
  const messages = Array.isArray(messageRecords) ? messageRecords : [messageRecords];

  for (const record of messages) {
    const msgId = record.id;
    if (!msgId || processedIds.has(msgId)) continue;

    const authorId = record.author?.id ?? (Array.isArray(record.author_id) ? record.author_id[0] : null);
    if (authorId === client.partnerIdValue) continue;

    try {
      const fullMessages = await client.call(
        "mail.message",
        "search_read",
        [[["id", "=", msgId]]],
        { fields: ["body", "author_id", "model", "res_id", "record_name", "date"] },
      );
      if (fullMessages && fullMessages.length > 0) {
        const formatted = client.formatMessage(fullMessages[0]);
        if (formatted) {
          log?.(`[odoo:${account.accountId}] WS message: ${formatted.sessionKey} from ${formatted.senderName}`);
          await dispatchToAgent(formatted, account, config, log, error);
          track(msgId);
        }
      }
    } catch (err) {
      error?.(`[odoo:${account.accountId}] failed to fetch message ${msgId}: ${err}`);
    }
  }
}

async function processNewMessage(
  payload: any,
  client: OdooClient,
  account: ResolvedOdooAccount,
  processedIds: Set<number>,
  track: (id: number) => void,
  config: OpenClawConfig,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  try {
    const data = payload?.data ?? payload;
    const messageRecords = data?.["mail.message"] ?? data?.Message ?? [];
    const messages = Array.isArray(messageRecords) ? messageRecords : [messageRecords];
    if (messages.length === 0) return;

    for (const messageData of messages) {
      const msgId = messageData.id;
      if (!msgId || processedIds.has(msgId)) continue;

      const authorId = messageData.author_id ?? messageData.author?.id;
      if (authorId === client.partnerIdValue) continue;

      const fullMessages = await client.call(
        "mail.message",
        "search_read",
        [[["id", "=", msgId]]],
        { fields: ["body", "author_id", "model", "res_id", "record_name", "date"] },
      );
      if (fullMessages && fullMessages.length > 0) {
        const formatted = client.formatMessage(fullMessages[0]);
        if (formatted) {
          log?.(`[odoo:${account.accountId}] new_message: ${formatted.sessionKey} from ${formatted.senderName}`);
          await dispatchToAgent(formatted, account, config, log, error);
          track(msgId);
        }
      }
    }
  } catch (err) {
    error?.(`[odoo:${account.accountId}] processNewMessage error: ${err}`);
  }
}

async function dispatchToAgent(
  formatted: FormattedOdooMessage,
  account: ResolvedOdooAccount,
  config: OpenClawConfig,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  try {
    const runtime = getOdooRuntime();
    const isGroup = formatted.model === "discuss.channel";

    const routingHelper = runtime?.channel?.routing;
    if (!routingHelper?.resolveInboundRouteEnvelopeBuilder) {
      log?.(`[odoo:${account.accountId}] runtime routing not available, trying compat...`);
      const compat = await import("openclaw/plugin-sdk/compat");
      const { route, buildEnvelope } = (compat as any).resolveInboundRouteEnvelopeBuilderWithRuntime({
        cfg: config,
        channel: "odoo",
        accountId: account.accountId,
        peer: { kind: isGroup ? "group" : "direct", id: formatted.sessionKey },
        runtime: runtime?.channel,
      });

      const { body } = buildEnvelope({
        channel: "Odoo",
        from: formatted.senderName,
        body: formatted.message,
      });

      const replyHelper = runtime?.channel?.reply;
      if (!replyHelper?.finalizeInboundContext) {
        error?.(`[odoo:${account.accountId}] runtime reply pipeline not available — message received but cannot dispatch: ${formatted.message}`);
        return;
      }

      const ctxPayload = replyHelper.finalizeInboundContext({
        Body: body,
        BodyForAgent: formatted.message,
        RawBody: formatted.message,
        CommandBody: formatted.message,
        From: `odoo:${formatted.senderId}`,
        To: `odoo:${formatted.model}:${formatted.resId}`,
        SessionKey: route.sessionKey,
        AccountId: route.accountId,
        ChatType: isGroup ? "channel" : "direct",
        ConversationLabel: `${formatted.model}/${formatted.resId}`,
        SenderName: formatted.senderName,
        SenderId: String(formatted.senderId),
        Provider: "odoo",
        Surface: "odoo",
        MessageSid: formatted.idempotencyKey,
        MessageSidFull: formatted.idempotencyKey,
        OriginatingChannel: "odoo",
        OriginatingTo: `odoo:${formatted.model}:${formatted.resId}`,
      });

      await replyHelper.dispatchReplyWithBufferedBlockDispatcher({
        ctx: ctxPayload,
        cfg: config,
        dispatcherOptions: {
          deliver: async (payload: any) => {
            await deliverOdooReply(payload, account, formatted, log, error);
          },
        },
      });
      return;
    }

    const { route, buildEnvelope } = routingHelper.resolveInboundRouteEnvelopeBuilder({
      cfg: config,
      channel: "odoo",
      accountId: account.accountId,
      peer: { kind: isGroup ? "group" : "direct", id: formatted.sessionKey },
    });

    const { body } = buildEnvelope({
      channel: "Odoo",
      from: formatted.senderName,
      body: formatted.message,
    });

    const ctxPayload = runtime.channel.reply.finalizeInboundContext({
      Body: body,
      BodyForAgent: formatted.message,
      RawBody: formatted.message,
      CommandBody: formatted.message,
      From: `odoo:${formatted.senderId}`,
      To: `odoo:${formatted.model}:${formatted.resId}`,
      SessionKey: route.sessionKey,
      AccountId: route.accountId,
      ChatType: isGroup ? "channel" : "direct",
      ConversationLabel: `${formatted.model}/${formatted.resId}`,
      SenderName: formatted.senderName,
      SenderId: String(formatted.senderId),
      Provider: "odoo",
      Surface: "odoo",
      MessageSid: formatted.idempotencyKey,
      MessageSidFull: formatted.idempotencyKey,
      OriginatingChannel: "odoo",
      OriginatingTo: `odoo:${formatted.model}:${formatted.resId}`,
    });

    await runtime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({
      ctx: ctxPayload,
      cfg: config,
      dispatcherOptions: {
        deliver: async (payload: any) => {
          await deliverOdooReply(payload, account, formatted, log, error);
        },
      },
    });
  } catch (err) {
    error?.(`[odoo:${account.accountId}] dispatch error: ${err}`);
  }
}

async function deliverOdooReply(
  payload: any,
  account: ResolvedOdooAccount,
  original: FormattedOdooMessage,
  log?: (...args: any[]) => void,
  error?: (...args: any[]) => void,
): Promise<void> {
  try {
    const { sendOdooMessage } = await import("./send.js");
    const text = payload.text ?? payload.body ?? "";
    if (!text) return;

    log?.(`[odoo:${account.accountId}] sending reply to ${original.sessionKey}`);
    await sendOdooMessage({
      account,
      sessionKey: original.sessionKey,
      text,
    });
  } catch (err) {
    error?.(`[odoo:${account.accountId}] reply delivery error: ${err}`);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
