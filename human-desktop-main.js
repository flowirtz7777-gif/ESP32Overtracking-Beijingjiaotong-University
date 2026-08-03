"use strict";

const { app, BrowserWindow, shell } = require("electron");
const path = require("path");
const fs = require("fs");

const WINDOW_TITLE = "人工驾驶仿真软件";
const PRIMARY_HTML = path.join(
  __dirname,
  "人工驾驶仿真软件",
  "人工驾驶仿真软件.html"
);
const FALLBACK_HTML = path.join(
  __dirname,
  "人工驾驶仿真软件",
  "index.html"
);

function resolveEntryFile() {
  if (fs.existsSync(PRIMARY_HTML)) return PRIMARY_HTML;
  if (fs.existsSync(FALLBACK_HTML)) return FALLBACK_HTML;
  return null;
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 950,
    minWidth: 1100,
    minHeight: 760,
    autoHideMenuBar: true,
    title: WINDOW_TITLE,
    icon: path.join(__dirname, "交大校徽.png"),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true
    }
  });

  mainWindow.on("page-title-updated", (event) => {
    event.preventDefault();
    mainWindow.setTitle(WINDOW_TITLE);
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  const entryFile = resolveEntryFile();
  if (!entryFile) {
    console.error("[human-driving] HTML entry not found:", PRIMARY_HTML, FALLBACK_HTML);
    mainWindow.close();
    return;
  }

  mainWindow.loadFile(entryFile).catch((error) => {
    console.error("[human-driving] loadFile failed:", error.message);
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
