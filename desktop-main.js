const { app, BrowserWindow, shell, session } = require("electron");
const path = require("path");

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1540,
    height: 980,
    minWidth: 1200,
    minHeight: 760,
    autoHideMenuBar: true,
    backgroundColor: "#07111f",
    title: "PID工况仿真导出器",
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      devTools: true
    }
  });

  mainWindow.loadFile(path.join(__dirname, "pid工况仿真导出器.html"));

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(() => {
  const electronSession = session.defaultSession;
  electronSession.on("will-download", (event, item) => {
    item.setSaveDialogOptions({
      title: "导出 PID 工况 CSV",
      defaultPath: item.getFilename()
    });
  });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
