/**
 * Odoo JSON-RPC + WebSocket bus client.
 * Uses native fetch for HTTP and the ws library for WebSocket.
 */

import WebSocket from "ws";
import type { OdooMailMessage, OdooNotification } from "./types.js";
import { htmlToText } from "./html.js";
import { buildOdooSessionKey, extractHostname } from "./session-key.js";

const PRESENCE_INTERVAL_MS = 50_000;
const KEEPALIVE_INTERVAL_MS = 60_000;

export type OdooClientConfig = {
  url: string;
  db: string;
  login: string;
  password: string;
};

export type FormattedOdooMessage = {
  message: string;
  sessionKey: string;
  idempotencyKey: string;
  senderName: string;
  senderId: number;
  model: string;
  resId: number;
};

export class OdooClient {
  private config: OdooClientConfig;
  private sessionCookie: string | null = null;
  private uid: number | null = null;
  private partnerId: number | null = null;
  private lastNotifId = 0;
  private hostname: string;

  constructor(config: OdooClientConfig) {
    this.config = config;
    this.hostname = extractHostname(config.url);
  }

  get partnerIdValue(): number {
    if (this.partnerId === null) throw new Error("Not authenticated");
    return this.partnerId;
  }

  async connect(): Promise<void> {
    const result = await this.jsonrpc("/web/session/authenticate", {
      db: this.config.db,
      login: this.config.login,
      password: this.config.password,
    });
    this.uid = result?.uid;
    if (!this.uid) {
      throw new Error("Odoo authentication failed — check credentials");
    }
    this.partnerId = result.partner_id;
  }

  private async jsonrpc(path: string, params: Record<string, unknown> = {}): Promise<any> {
    const url = this.config.url + path;
    const payload = {
      jsonrpc: "2.0",
      method: "call",
      id: 1,
      params,
    };

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.sessionCookie) {
      headers["Cookie"] = this.sessionCookie;
    }

    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    const setCookie = resp.headers.get("set-cookie");
    if (setCookie) {
      const sessionMatch = setCookie.match(/session_id=([^;]+)/);
      if (sessionMatch) {
        this.sessionCookie = `session_id=${sessionMatch[1]}`;
      }
    }

    const data = (await resp.json()) as any;
    if (data.error) {
      const err = data.error;
      const msg = err.data?.message ?? err.message ?? JSON.stringify(err);
      throw new Error(`Odoo JSON-RPC error: ${msg}`);
    }
    return data.result;
  }

  async call(
    model: string,
    method: string,
    args: unknown[] = [],
    kwargs: Record<string, unknown> = {},
  ): Promise<any> {
    return await this.jsonrpc("/web/dataset/call_kw", {
      model,
      method,
      args,
      kwargs,
    });
  }

  async getUnreadNotifications(): Promise<{
    messages: OdooMailMessage[];
    notifIds: number[];
  }> {
    const notifRecords = (await this.call(
      "mail.notification",
      "search_read",
      [
        [
          ["res_partner_id", "=", this.partnerIdValue],
          ["is_read", "=", false],
        ],
      ],
      { fields: ["id", "mail_message_id"], limit: 100 },
    )) as OdooNotification[];

    if (!notifRecords || notifRecords.length === 0) {
      return { messages: [], notifIds: [] };
    }

    const notifIds = notifRecords.map((n) => n.id);
    const messageIds = [...new Set(notifRecords.map((n) => n.mail_message_id[0]))];

    const messages = (await this.call(
      "mail.message",
      "search_read",
      [[["id", "in", messageIds]]],
      {
        fields: ["body", "author_id", "model", "res_id", "record_name", "date"],
      },
    )) as OdooMailMessage[];

    return { messages, notifIds };
  }

  async markNotificationsRead(notifIds: number[]): Promise<void> {
    if (notifIds.length === 0) return;
    await this.call("mail.notification", "write", [notifIds, { is_read: true }]);
  }

  async postMessage(params: {
    model: string;
    resId: number;
    body: string;
    partnerIds?: number[];
  }): Promise<void> {
    const isDiscussChannel = params.model === "discuss.channel";
    const subtypeXmlId = isDiscussChannel ? "mail.mt_comment" : "mail.mt_note";

    await this.call(params.model, "message_post", [[params.resId]], {
      body: params.body,
      body_is_html: true,
      message_type: "comment",
      subtype_xmlid: subtypeXmlId,
      partner_ids: params.partnerIds ?? [],
    });
  }

  formatMessage(msg: OdooMailMessage): FormattedOdooMessage | null {
    const bodyPlain = htmlToText(msg.body || "");
    if (!bodyPlain) return null;

    const author = Array.isArray(msg.author_id) ? msg.author_id[1] : "Unknown";
    const authorId = Array.isArray(msg.author_id) ? msg.author_id[0] : 0;
    const recordName = msg.record_name || "";
    const resModel = msg.model || "";
    const resId = msg.res_id || 0;

    const parts: string[] = [];
    if (resModel && resId) {
      const namePart = recordName ? `, name=${recordName}` : "";
      parts.push(`[Odoo record: res.model=${resModel}, res.id=${resId}${namePart}]`);
    }
    parts.push(`${author}: ${bodyPlain}`);

    return {
      message: parts.join("\n"),
      sessionKey: buildOdooSessionKey(this.hostname, resModel, resId),
      idempotencyKey: String(msg.id),
      senderName: author,
      senderId: authorId,
      model: resModel,
      resId,
    };
  }

  listenBus(params: {
    onNotifications: (notifications: any[]) => void;
    onError: (error: Error) => void;
    onClose: () => void;
    signal?: AbortSignal;
  }): void {
    const wsUrl = this.config.url
      .replace(/^http:/, "ws:")
      .replace(/^https:/, "wss:")
      + "/websocket";

    const headers: Record<string, string> = {
      Origin: this.config.url,
    };
    if (this.sessionCookie) {
      headers["Cookie"] = this.sessionCookie;
    }

    const ws = new WebSocket(wsUrl, { headers });
    let presenceTimer: ReturnType<typeof setInterval> | null = null;
    let keepaliveTimer: ReturnType<typeof setInterval> | null = null;

    const cleanup = () => {
      if (presenceTimer) clearInterval(presenceTimer);
      if (keepaliveTimer) clearInterval(keepaliveTimer);
      presenceTimer = null;
      keepaliveTimer = null;
    };

    if (params.signal) {
      params.signal.addEventListener("abort", () => {
        cleanup();
        ws.close();
      });
    }

    ws.on("open", () => {
      ws.send(
        JSON.stringify({
          event_name: "subscribe",
          data: { channels: [], last: this.lastNotifId },
        }),
      );

      ws.send(JSON.stringify({ event_name: "update_presence", data: { inactivity_period: 0 } }));

      presenceTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ event_name: "update_presence", data: { inactivity_period: 0 } }));
        }
      }, PRESENCE_INTERVAL_MS);

      keepaliveTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(new Uint8Array([0x00]));
        }
      }, KEEPALIVE_INTERVAL_MS);
    });

    ws.on("message", (data) => {
      try {
        const raw = data.toString();
        const notifications = JSON.parse(raw);
        if (!Array.isArray(notifications)) return;
        if (notifications.length > 0) {
          this.lastNotifId = Math.max(...notifications.map((n: any) => n.id));
        }
        params.onNotifications(notifications);
      } catch {
        // Ignore parse errors (binary frames, etc.)
      }
    });

    ws.on("close", () => {
      cleanup();
      params.onClose();
    });

    ws.on("error", (err) => {
      cleanup();
      params.onError(err instanceof Error ? err : new Error(String(err)));
    });
  }
}
