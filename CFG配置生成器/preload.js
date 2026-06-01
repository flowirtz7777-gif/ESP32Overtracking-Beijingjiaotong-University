const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("cfgBuilder", {
  saveCfg: (filename, content) => ipcRenderer.invoke("save-cfg", { filename, content })
});
