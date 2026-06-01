const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const path = require("path");

function createWindow() {
  const win = new BrowserWindow({
    width: 1120,
    height: 820,
    minWidth: 980,
    minHeight: 700,
    backgroundColor: "#ffffff",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile(path.join(__dirname, "index.html"));
}

ipcMain.handle("save-cfg", async (_event, payload) => {
  const repo = path.dirname(__dirname);
  const dir = path.join(repo, "转弯全过程盲区分析软件", "CFG配置");
  fs.mkdirSync(dir, { recursive: true });
  const safeName = path.basename(payload.filename).replace(/[<>:"/\\|?*]/g, "_");
  const filePath = path.join(dir, safeName);
  fs.writeFileSync(filePath, payload.content, "utf8");
  return filePath;
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
