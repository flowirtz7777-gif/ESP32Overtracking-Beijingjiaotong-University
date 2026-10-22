const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const path = require("path");

function createWindow() {
  const win = new BrowserWindow({
    width: 1500,
    height: 930,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#0b1118",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile(path.join(__dirname, "index.html"));
}

ipcMain.handle("save-csv", async (_event, payload) => {
  const dirs = {
    targets: path.join(__dirname, "目标点CSV"),
    logs: path.join(__dirname, "边界点盲区日志"),
    cfg: path.join(__dirname, "CFG配置")
  };
  const dir = dirs[payload.kind];
  if (!dir) throw new Error("Unknown CSV kind");
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
