// 我的日程 · Windows 安装程序
// 编译：csc /target:winexe /win32icon:..\assets\icon.ico /resource:payload.zip,payload.zip ...
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("我的日程 安装程序")]
[assembly: AssemblyProduct("我的日程")]
[assembly: AssemblyDescription("日历 · 日程提醒 · 节假日提醒 · 月度图表总结")]
[assembly: AssemblyCompany("我的日程")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace MyScheduleSetup
{
    internal static class AppInfo
    {
        public const string Name = "我的日程";
        public const string AppId = "MySchedule.Desktop";
        public const string Version = "1.1.0";
        public const string Publisher = "我的日程";
        public const string ResourceName = "payload.zip";
    }

    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            string arguments = (args == null) ? "" : string.Join(" ", args);
            Log("启动 setup，参数: " + arguments);
            AppDomain.CurrentDomain.UnhandledException += delegate(object sender, UnhandledExceptionEventArgs e)
            {
                Log("未处理异常: " + e.ExceptionObject);
            };

            bool silent = HasArg(args, "/S") || HasArg(args, "--silent");
            string dir = GetArg(args, "--dir", Installer.DefaultInstallDir);

            if (silent)
            {
                try
                {
                    Installer.Install(dir, true, true, delegate(int percent, string message) { });
                    Log("静默安装完成: " + dir);
                    return 0;
                }
                catch (Exception ex)
                {
                    Log("静默安装失败: " + ex);
                    return 1;
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
            return 0;
        }

        private static bool HasArg(string[] args, string flag)
        {
            if (args == null) return false;
            foreach (string arg in args)
            {
                if (string.Equals(arg, flag, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        private static string GetArg(string[] args, string name, string fallback)
        {
            if (args != null)
            {
                for (int i = 0; i < args.Length - 1; i++)
                {
                    if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return args[i + 1];
                }
            }
            return fallback;
        }

        internal static void Log(string message)
        {
            try
            {
                string path = Path.Combine(Path.GetTempPath(), "myschedule-setup.log");
                File.AppendAllText(path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message + Environment.NewLine, Encoding.UTF8);
            }
            catch (Exception)
            {
            }
        }
    }

    // ------------------------------------------------------------------ 安装逻辑
    internal static class Installer
    {
        public static string DefaultInstallDir
        {
            get
            {
                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs", AppInfo.Name);
            }
        }

        public static void Install(string targetDir, bool desktopShortcut, bool autostart, Action<int, string> report)
        {
            if (string.IsNullOrEmpty(targetDir)) throw new ArgumentException("安装路径不能为空");
            targetDir = Path.GetFullPath(targetDir).TrimEnd('\\');
            if (targetDir.Length <= 3) throw new ArgumentException("请选择具体的安装文件夹");

            Report(report, 2, "准备安装目录…");
            Directory.CreateDirectory(targetDir);
            KillProcessesIn(targetDir);

            Extract(targetDir, report);

            Report(report, 82, "写入初始数据目录…");
            string dataDir = Path.Combine(targetDir, "data");
            SafeStep("初始化数据目录", delegate
            {
                Directory.CreateDirectory(dataDir);
                File.WriteAllText(Path.Combine(dataDir, "notify-appid.txt"), AppInfo.AppId, new UTF8Encoding(false));
            });

            Report(report, 86, "创建快捷方式…");
            SafeStep("创建快捷方式", delegate { CreateShortcuts(targetDir, desktopShortcut, autostart); });

            Report(report, 92, "注册通知身份…");
            SafeStep("注册通知身份", delegate { RegisterNotificationIdentity(targetDir); });

            Report(report, 96, "写入卸载信息…");
            SafeStep("写入卸载信息", delegate { WriteUninstallEntry(targetDir); });

            Report(report, 100, "安装完成");
        }

        private static void SafeStep(string name, Action action)
        {
            try
            {
                action();
            }
            catch (Exception ex)
            {
                Program.Log(name + " 失败（已跳过）: " + ex.Message);
            }
        }

        public static void Launch(string dir)
        {
            try
            {
                string pythonw = Path.Combine(dir, "runtime", "pythonw.exe");
                string appPy = Path.Combine(dir, "backend", "app.py");
                if (!File.Exists(pythonw) || !File.Exists(appPy)) return;
                ProcessStartInfo info = new ProcessStartInfo(pythonw, "\"" + appPy + "\"");
                info.WorkingDirectory = dir;
                info.UseShellExecute = false;
                Process.Start(info);
            }
            catch (Exception ex)
            {
                Program.Log("启动失败: " + ex.Message);
            }
        }

        private static void Report(Action<int, string> report, int percent, string message)
        {
            if (report != null) report(percent, message);
        }

        public static void Extract(string targetDir, Action<int, string> report)
        {
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream stream = assembly.GetManifestResourceStream(AppInfo.ResourceName))
            {
                if (stream == null) throw new InvalidOperationException("安装包数据损坏（缺少 payload）");
                using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
                {
                    int total = archive.Entries.Count;
                    int index = 0;
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        index++;
                        string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                        string destination = Path.Combine(targetDir, relative);
                        if (entry.FullName.EndsWith("/") || entry.Name.Length == 0)
                        {
                            Directory.CreateDirectory(destination);
                        }
                        else
                        {
                            string folder = Path.GetDirectoryName(destination);
                            if (!string.IsNullOrEmpty(folder)) Directory.CreateDirectory(folder);
                            if (File.Exists(destination))
                            {
                                try { File.SetAttributes(destination, FileAttributes.Normal); }
                                catch (Exception) { }
                            }
                            entry.ExtractToFile(destination, true);
                        }
                        if (report != null && (index % 25 == 0 || index == total))
                        {
                            report(6 + index * 74 / total, "正在解压文件…（" + index + " / " + total + "）");
                        }
                    }
                }
            }
        }

        private static void CreateShortcuts(string dir, bool desktopShortcut, bool autostart)
        {
            string pythonw = Path.Combine(dir, "runtime", "pythonw.exe");
            string appPy = Path.Combine(dir, "backend", "app.py");
            string arguments = "\"" + appPy + "\"";
            string icon = Path.Combine(dir, "assets", "icon.ico");
            string description = AppInfo.Name + " · 日程与提醒";

            string startMenu = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Programs), AppInfo.Name + ".lnk");
            ShellLink.Create(startMenu, pythonw, arguments, dir, icon, description);

            if (desktopShortcut)
            {
                string desktop = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), AppInfo.Name + ".lnk");
                ShellLink.Create(desktop, pythonw, arguments, dir, icon, description);
            }

            string startup = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Startup), AppInfo.Name + ".lnk");
            if (autostart) ShellLink.Create(startup, pythonw, arguments + " --boot", dir, icon, description);
            else ShellLink.Delete(startup);
        }

        private static void RegisterNotificationIdentity(string dir)
        {
            string subKey = @"Software\Classes\AppUserModelId\" + AppInfo.AppId;
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(subKey))
            {
                if (key != null)
                {
                    key.SetValue("DisplayName", AppInfo.Name);
                    key.SetValue("IconUri", Path.Combine(dir, "assets", "icon.png"));
                    key.SetValue("ShowInSettings", 1, RegistryValueKind.DWord);
                }
            }
        }

        private static void WriteUninstallEntry(string dir)
        {
            long size = 0;
            try
            {
                foreach (string file in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                {
                    try { size += new FileInfo(file).Length; }
                    catch (Exception) { }
                }
            }
            catch (Exception) { }
            int sizeKb = (int)Math.Min(int.MaxValue, size / 1024);

            string uninstall = Path.Combine(dir, "uninstall.exe");
            string icon = Path.Combine(dir, "assets", "icon.ico");
            string subKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppInfo.AppId;
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(subKey))
            {
                if (key == null) return;
                key.SetValue("DisplayName", AppInfo.Name);
                key.SetValue("DisplayVersion", AppInfo.Version);
                key.SetValue("Publisher", AppInfo.Publisher);
                key.SetValue("InstallLocation", dir);
                key.SetValue("DisplayIcon", icon);
                key.SetValue("UninstallString", "\"" + uninstall + "\"");
                key.SetValue("QuietUninstallString", "\"" + uninstall + "\" /S");
                key.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
                key.SetValue("EstimatedSize", sizeKb, RegistryValueKind.DWord);
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
        }

        public static void KillProcessesIn(string dir)
        {
            string root = Path.GetFullPath(dir).TrimEnd('\\') + "\\";
            int self = Process.GetCurrentProcess().Id;
            Process[] processes = Process.GetProcesses();
            foreach (Process process in processes)
            {
                try
                {
                    if (process.Id == self) continue;
                    string file = process.MainModule.FileName;
                    if (file == null) continue;
                    if (!file.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;
                    process.Kill();
                    process.WaitForExit(3000);
                }
                catch (Exception)
                {
                }
                finally
                {
                    try { process.Dispose(); }
                    catch (Exception) { }
                }
            }
        }
    }

    // ------------------------------------------------------------------ 快捷方式
    internal static class ShellLink
    {
        public static void Create(string lnkPath, string target, string arguments,
                                  string workDir, string iconPath, string description)
        {
            object shell = null;
            object link = null;
            try
            {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                if (shellType == null) return;
                shell = Activator.CreateInstance(shellType);
                link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell,
                    new object[] { lnkPath });
                Type linkType = link.GetType();
                linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { target });
                linkType.InvokeMember("Arguments", BindingFlags.SetProperty, null, link, new object[] { arguments });
                linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { workDir });
                linkType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, link, new object[] { iconPath });
                linkType.InvokeMember("Description", BindingFlags.SetProperty, null, link, new object[] { description });
                linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
            }
            catch (Exception ex)
            {
                Program.Log("创建快捷方式失败 " + lnkPath + ": " + ex.Message);
            }
            finally
            {
                ReleaseCom(link);
                ReleaseCom(shell);
            }
        }

        public static void Delete(string lnkPath)
        {
            try
            {
                if (File.Exists(lnkPath)) File.Delete(lnkPath);
            }
            catch (Exception ex)
            {
                Program.Log("删除快捷方式失败 " + lnkPath + ": " + ex.Message);
            }
        }

        private static void ReleaseCom(object instance)
        {
            if (instance == null) return;
            try
            {
                if (Marshal.IsComObject(instance)) Marshal.ReleaseComObject(instance);
            }
            catch (Exception) { }
        }
    }

    // ------------------------------------------------------------------ 界面
    internal sealed class SetupForm : Form
    {
        private readonly TextBox _pathBox;
        private readonly CheckBox _deskBox;
        private readonly CheckBox _autoBox;
        private readonly CheckBox _runBox;
        private readonly ProgressBar _bar;
        private readonly Label _status;
        private readonly Button _installBtn;
        private readonly Button _closeBtn;
        private bool _busy;
        private bool _installed;

        public SetupForm()
        {
            SuspendLayout();
            Text = "我的日程 · 安装程序";
            ClientSize = new Size(600, 486);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.White;
            AutoScaleMode = AutoScaleMode.None;
            Font = new Font("Microsoft YaHei UI", 9F);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
            catch (Exception) { }

            Panel header = new Panel();
            header.Bounds = new Rectangle(0, 0, 600, 96);
            header.BackColor = Color.FromArgb(69, 103, 242);
            header.Paint += PaintHeader;
            Controls.Add(header);

            Label tip = new Label();
            tip.Text = "将「我的日程」安装到下面的文件夹：";
            tip.ForeColor = Color.FromArgb(113, 128, 150);
            tip.Bounds = new Rectangle(32, 116, 536, 20);
            Controls.Add(tip);

            _pathBox = new TextBox();
            _pathBox.Text = Installer.DefaultInstallDir;
            _pathBox.Bounds = new Rectangle(32, 140, 424, 28);
            Controls.Add(_pathBox);

            Button browse = new Button();
            browse.Text = "浏览…";
            browse.Bounds = new Rectangle(462, 139, 106, 30);
            StyleSecondary(browse);
            browse.Click += BrowseClick;
            Controls.Add(browse);

            _deskBox = MakeCheck("创建桌面快捷方式", 190, true);
            _autoBox = MakeCheck("开机自动启动，并在开机时提醒当天的待办", 220, true);
            _runBox = MakeCheck("安装完成后立即运行", 250, true);

            Label note = new Label();
            note.Text = "已包含 Python 运行时，安装后约占用 46 MB；安装到当前用户目录，无需管理员权限。"
                      + "应用只在本地运行，日程数据仅保存在本机，不会联网上传。";
            note.ForeColor = Color.FromArgb(152, 163, 183);
            note.Bounds = new Rectangle(32, 294, 536, 46);
            Controls.Add(note);

            _bar = new ProgressBar();
            _bar.Bounds = new Rectangle(32, 352, 536, 8);
            _bar.Visible = false;
            _bar.Minimum = 0;
            _bar.Maximum = 100;
            Controls.Add(_bar);

            _status = new Label();
            _status.Text = "";
            _status.ForeColor = Color.FromArgb(113, 128, 150);
            _status.Bounds = new Rectangle(32, 368, 536, 22);
            Controls.Add(_status);

            _installBtn = new Button();
            _installBtn.Text = "开始安装";
            _installBtn.Bounds = new Rectangle(352, 412, 216, 44);
            StylePrimary(_installBtn);
            _installBtn.Click += InstallClick;
            Controls.Add(_installBtn);

            _closeBtn = new Button();
            _closeBtn.Text = "关闭";
            _closeBtn.Bounds = new Rectangle(258, 412, 84, 44);
            StyleSecondary(_closeBtn);
            _closeBtn.Click += delegate { if (!_busy) Close(); };
            Controls.Add(_closeBtn);

            AcceptButton = _installBtn;
            ResumeLayout(false);
            PerformLayout();
        }

        private void PaintHeader(object sender, PaintEventArgs e)
        {
            Rectangle rect = new Rectangle(0, 0, 600, 96);
            using (LinearGradientBrush brush = new LinearGradientBrush(rect,
                Color.FromArgb(139, 92, 246), Color.FromArgb(69, 103, 242), LinearGradientMode.Horizontal))
            {
                e.Graphics.FillRectangle(brush, rect);
            }
            try
            {
                using (Icon icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath))
                {
                    if (icon != null) e.Graphics.DrawIcon(icon, new Rectangle(28, 28, 40, 40));
                }
            }
            catch (Exception) { }

            using (Font titleFont = new Font("Microsoft YaHei UI", 15F, FontStyle.Bold))
            using (Font subFont = new Font("Microsoft YaHei UI", 9F))
            using (SolidBrush white = new SolidBrush(Color.White))
            using (SolidBrush soft = new SolidBrush(Color.FromArgb(228, 234, 255)))
            {
                e.Graphics.DrawString("我的日程", titleFont, white, 82, 22);
                e.Graphics.DrawString("日历 · 日程提醒 · 节假日提醒 · 月度图表总结     版本 " + AppInfo.Version,
                    subFont, soft, 84, 56);
            }
        }

        private CheckBox MakeCheck(string text, int top, bool value)
        {
            CheckBox box = new CheckBox();
            box.Text = text;
            box.Checked = value;
            box.Bounds = new Rectangle(32, top, 536, 24);
            box.ForeColor = Color.FromArgb(55, 66, 88);
            Controls.Add(box);
            return box;
        }

        private static void StylePrimary(Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.BackColor = Color.FromArgb(69, 103, 242);
            button.ForeColor = Color.White;
            button.Font = new Font("Microsoft YaHei UI", 10F, FontStyle.Bold);
            button.Cursor = Cursors.Hand;
        }

        private static void StyleSecondary(Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Color.FromArgb(214, 221, 233);
            button.FlatAppearance.BorderSize = 1;
            button.BackColor = Color.White;
            button.ForeColor = Color.FromArgb(58, 71, 97);
            button.Cursor = Cursors.Hand;
        }

        private void BrowseClick(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择安装位置";
                dialog.ShowNewFolderButton = true;
                try { dialog.SelectedPath = _pathBox.Text; }
                catch (Exception) { }
                if (dialog.ShowDialog(this) == DialogResult.OK) _pathBox.Text = dialog.SelectedPath;
            }
        }

        private void InstallClick(object sender, EventArgs e)
        {
            if (_installed)
            {
                Close();
                return;
            }
            if (_busy) return;

            string dir = _pathBox.Text.Trim();
            if (dir.Length == 0)
            {
                MessageBox.Show(this, "请填写安装路径。", AppInfo.Name, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            try
            {
                Path.GetFullPath(dir);
            }
            catch (Exception)
            {
                MessageBox.Show(this, "安装路径格式不正确，请重新选择。", AppInfo.Name,
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            _busy = true;
            _pathBox.Enabled = false;
            _deskBox.Enabled = false;
            _autoBox.Enabled = false;
            _runBox.Enabled = false;
            _installBtn.Enabled = false;
            _closeBtn.Enabled = false;
            _bar.Visible = true;
            _bar.Value = 0;
            _status.Text = "正在准备安装…";

            bool desktop = _deskBox.Checked;
            bool autostart = _autoBox.Checked;
            Thread worker = new Thread(delegate()
            {
                try
                {
                    Installer.Install(dir, desktop, autostart, Report);
                    BeginInvoke(new Action(FinishOk));
                }
                catch (Exception ex)
                {
                    Program.Log("安装失败: " + ex);
                    string message = ex.Message;
                    BeginInvoke(new Action(delegate { FinishError(message); }));
                }
            });
            worker.IsBackground = true;
            worker.Start();
        }

        private void Report(int percent, string message)
        {
            if (InvokeRequired)
            {
                try { BeginInvoke(new Action<int, string>(Report), new object[] { percent, message }); }
                catch (Exception) { }
                return;
            }
            if (percent < 0) percent = 0;
            if (percent > 100) percent = 100;
            if (_bar.Value != percent) _bar.Value = percent;
            if (!string.IsNullOrEmpty(message)) _status.Text = message;
        }

        private void FinishOk()
        {
            _busy = false;
            _installed = true;
            _bar.Value = 100;
            _installBtn.Text = "完成";
            _installBtn.Enabled = true;
            _closeBtn.Enabled = true;
            string dir = Path.GetFullPath(_pathBox.Text.Trim());
            _status.Text = "安装完成：" + dir;
            if (_runBox.Checked) Installer.Launch(dir);
        }

        private void FinishError(string message)
        {
            _busy = false;
            _bar.Visible = false;
            _status.Text = "安装失败，请查看日志 %TEMP%\\myschedule-setup.log";
            _pathBox.Enabled = true;
            _deskBox.Enabled = true;
            _autoBox.Enabled = true;
            _runBox.Enabled = true;
            _installBtn.Enabled = true;
            _closeBtn.Enabled = true;
            MessageBox.Show(this, "安装失败：" + message, AppInfo.Name,
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
