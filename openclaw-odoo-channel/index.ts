import type { ChannelPlugin } from "openclaw/plugin-sdk/compat";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk/compat";
import { odooPlugin } from "./src/channel.js";
import { setOdooRuntime } from "./src/runtime.js";

type OpenClawPluginApi = {
  runtime: any;
  registerChannel: (reg: { plugin: ChannelPlugin }) => void;
};

const plugin = {
  id: "odoo",
  name: "Odoo Discuss",
  description: "Odoo Discuss channel plugin — connects to Odoo messaging via WebSocket bus",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setOdooRuntime(api.runtime);
    api.registerChannel({ plugin: odooPlugin as ChannelPlugin });
  },
};

export default plugin;
