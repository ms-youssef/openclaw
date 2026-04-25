/** Odoo channel configuration for a single account. */
export type OdooAccountConfig = {
  enabled?: boolean;
  name?: string;
  /** Odoo instance base URL, e.g. "https://qddev.odoo.bemade.org" */
  url: string;
  /** Odoo database name */
  db: string;
  /** Odoo user login (email) */
  login: string;
  /** Odoo user password */
  password: string;
  /** Reconnect delay in seconds (default 5) */
  reconnectDelay?: number;
  /** Polling interval in seconds (default 15) */
  pollInterval?: number;
  /** Group policy: "open" | "allowlist" */
  groupPolicy?: string;
};

/** Odoo mail.message record from JSON-RPC. */
export type OdooMailMessage = {
  id: number;
  body: string;
  author_id: [number, string] | false;
  model: string;
  res_id: number;
  record_name: string;
  date: string;
};

/** Odoo mail.notification record. */
export type OdooNotification = {
  id: number;
  mail_message_id: [number, string];
};

/** Parsed Odoo session key components. */
export type OdooSessionKeyParts = {
  hostname: string;
  model: string;
  resId: number;
};
