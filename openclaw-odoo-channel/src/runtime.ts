import { createPluginRuntimeStore } from "openclaw/plugin-sdk/compat";

const { setRuntime: setOdooRuntime, getRuntime: getOdooRuntime } =
  createPluginRuntimeStore<any>("Odoo runtime not initialized");
export { getOdooRuntime, setOdooRuntime };
