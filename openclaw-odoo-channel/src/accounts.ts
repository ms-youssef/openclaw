import { DEFAULT_ACCOUNT_ID, normalizeAccountId } from "openclaw/plugin-sdk/compat";
import type { OdooAccountConfig } from "./types.js";

type OpenClawConfig = { channels?: Record<string, any>; [key: string]: any };

export type ResolvedOdooAccount = {
  accountId: string;
  name?: string;
  enabled: boolean;
  config: OdooAccountConfig;
  configured: boolean;
};

function resolveAccountConfig(
  cfg: OpenClawConfig,
  accountId: string,
): OdooAccountConfig | undefined {
  const accounts = cfg.channels?.["odoo"]?.accounts;
  if (!accounts || typeof accounts !== "object") {
    return undefined;
  }
  return accounts[accountId];
}

export function resolveOdooAccount(params: {
  cfg: OpenClawConfig;
  accountId?: string | null;
}): ResolvedOdooAccount {
  const accountId = normalizeAccountId(params.accountId);
  const baseEnabled = params.cfg.channels?.["odoo"]?.enabled !== false;
  const account = resolveAccountConfig(params.cfg, accountId);

  if (!account) {
    return {
      accountId,
      enabled: false,
      config: { url: "", db: "", login: "", password: "" },
      configured: false,
    };
  }

  const accountEnabled = account.enabled !== false;
  const configured = !!(account.url && account.db && account.login && account.password);

  return {
    accountId,
    name: account.name?.trim() || undefined,
    enabled: baseEnabled && accountEnabled,
    config: account,
    configured,
  };
}

export function listOdooAccountIds(cfg: OpenClawConfig): string[] {
  const accounts = cfg.channels?.["odoo"]?.accounts;
  if (!accounts || typeof accounts !== "object") {
    return [];
  }
  return Object.keys(accounts);
}

export function resolveDefaultOdooAccountId(cfg: OpenClawConfig): string {
  const ids = listOdooAccountIds(cfg);
  return ids.length > 0 ? ids[0] : DEFAULT_ACCOUNT_ID;
}

export function listEnabledOdooAccounts(cfg: OpenClawConfig): ResolvedOdooAccount[] {
  return listOdooAccountIds(cfg)
    .map((accountId) => resolveOdooAccount({ cfg, accountId }))
    .filter((account) => account.enabled && account.configured);
}
