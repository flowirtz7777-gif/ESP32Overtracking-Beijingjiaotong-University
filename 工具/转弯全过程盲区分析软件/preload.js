const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("blindspotApp", {
  saveCsv: (kind, filename, content) => ipcRenderer.invoke("save-csv", { kind, filename, content })
});
