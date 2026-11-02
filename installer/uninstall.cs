// 我的日程 · 卸载程序
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("我的日程 卸载程序")]
[assembly: AssemblyProduct("我的日程")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace MyScheduleUninstall
{
    internal static class AppInfo
    {
        public const string Name = "我的日程";
        public const string AppId = "MySchedule.Desktop";
    }

    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            string dir = Path.GetDirectoryName(Application.ExecutablePath);
            bool silent = HasArg(args, "/S") || HasArg(args, "--silent");
            bool purge = HasArg(args, "/purge") || HasArg(args, "--purge");

            if (silent)
            {
                try
                {
                    Remover.Run(dir, purge);
                    return 0;
                }
                catch (Exception ex)
                {
                    Log("静默卸载失败: " + ex);
                    return 1;
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new UninstallForm(dir));
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

        internal static void Log(string message)
        {
            try
            {
                string path = Path.Combine(Path.GetTempPath(), "myschedule-uninstall.log");
                File.AppendAllText(path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message + Environment.NewLine, Encoding.UTF8);
            }
            catch (Exception) { }
        }
    }

    internal static class Remover
    {
        public static void Run(string dir, bool purge)
        {
            dir = Path.GetFullPath(dir).TrimEnd('\\');
            KillProcessesIn(dir);
            RemoveShortcuts();
            RemoveRegistry();
            RemoveFiles(dir, purge);
            ScheduleSelfDelete(dir, purge);
        }

        private static void RemoveShortcuts()
        {
            DeleteIfExists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), AppInfo.Name + ".lnk"));
            DeleteIfExists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), AppInfo.Name + ".lnk"));
            DeleteIfExists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), AppInfo.Name + ".lnk"));
        }

        private static void DeleteIfExists(string path)
        {
            try
            {
                if (File.Exists(path)) File.Delete(path);
            }
            catch (Exception ex)
            {
                Program.Log("删除失败 " + path + ": " + ex.Message);
            }
        }

        private static void RemoveRegistry()
        {
            TryDeleteKey(@"Software\Classes\AppUserModelId\" + AppInfo.AppId);
            TryDeleteKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppInfo.AppId);
        }

        private static void TryDeleteKey(string subKey)
        {
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(subKey, false);
            }
            catch (Exception ex)
            {
                Program.Log("删除注册表失败 " + subKey + ": " + ex.Message);
            }
        }

        private static void RemoveFiles(string dir, bool purge)
        {
            string self = Path.GetFullPath(Application.ExecutablePath);

            foreach (string directory in SafeDirectories(dir))
            {
                if (!purge && string.Equals(Path.GetFileName(directory), "data", StringComparison.OrdinalIgnoreCase)) continue;
                TryDeleteDirectory(directory);
            }

            foreach (string file in SafeFiles(dir))
            {
                if (string.Equals(Path.GetFullPath(file), self, StringComparison.OrdinalIgnoreCase)) continue;
                try
                {
                    File.SetAttributes(file, FileAttributes.Normal);
                    File.Delete(file);
                }
                catch (Exception ex)
                {
                    Program.Log("删除文件失败 " + file + ": " + ex.Message);
                }
            }
        }

        private static string[] SafeDirectories(string dir)
        {
            try { return Directory.GetDirectories(dir); }
            catch (Exception) { return new string[0]; }
        }

        private static string[] SafeFiles(string dir)
        {
            try { return Directory.GetFiles(dir); }
            catch (Exception) { return new string[0]; }
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                if (!Directory.Exists(path)) return;
                foreach (string file in Directory.GetFiles(path, "*", SearchOption.AllDirectories))
                {
                    try { File.SetAttributes(file, FileAttributes.Normal); }
                    catch (Exception) { }
                }
                Directory.Delete(path, true);
            }
            catch (Exception ex)
            {
                Program.Log("删除目录失败 " + path + ": " + ex.Message);
            }
        }

        private static void KillProcessesIn(string dir)
        {
            string root = dir + "\\";
            int self = Process.GetCurrentProcess().Id;
            foreach (Process process in Process.GetProcesses())
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
                catch (Exception) { }
                finally
                {
                    try { process.Dispose(); }
                    catch (Exception) { }
                }
            }
        }

        private static void ScheduleSelfDelete(string dir, bool purge)
        {
            string self = Path.Combine(dir, "uninstall.exe");
            string script = Path.Combine(Path.GetTempPath(),
                "myschedule-uninstall-" + Guid.NewGuid().ToString("N") + ".cmd");
            StringBuilder builder = new StringBuilder();
            builder.AppendLine("@echo off");
            builder.AppendLine("ping -n 3 127.0.0.1 >nul");
            builder.AppendLine("del /f /q \"" + self + "\" >nul 2>&1");
            if (purge) builder.AppendLine("rd /s /q \"" + dir + "\" >nul 2>&1");
            else builder.AppendLine("rd \"" + dir + "\" >nul 2>&1");
            builder.AppendLine("del /f /q \"" + script + "\" >nul 2>&1");

            try
            {
                File.WriteAllText(script, builder.ToString(), Encoding.Default);
                ProcessStartInfo info = new ProcessStartInfo("cmd.exe", "/c \"" + script + "\"");
                info.CreateNoWindow = true;
                info.UseShellExecute = false;
                info.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(info);
            }
            catch (Exception ex)
            {
                Program.Log("安排自动删除失败: " + ex.Message);
            }
        }
    }

    internal sealed class UninstallForm : Form
    {
        private readonly string _dir;
        private readonly CheckBox _purgeBox;
        private readonly Button _runBtn;

        public UninstallForm(string dir)
        {
            _dir = Path.GetFullPath(dir);
            SuspendLayout();
            Text = "卸载 我的日程";
            ClientSize = new Size(520, 330);
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
            header.Bounds = new Rectangle(0, 0, 520, 88);
            header.Paint += PaintHeader;
            Controls.Add(header);

            Label title = new Label();
            title.Text = "确定要卸载「我的日程」吗？";
            title.Font = new Font("Microsoft YaHei UI", 11F, FontStyle.Bold);
            title.ForeColor = Color.FromArgb(23, 32, 51);
            title.Bounds = new Rectangle(32, 112, 456, 26);
            Controls.Add(title);

            Label text = new Label();
            text.Text = "将移除程序文件、快捷方式与通知身份。";
            text.ForeColor = Color.FromArgb(113, 128, 150);
            text.Bounds = new Rectangle(32, 144, 456, 22);
            Controls.Add(text);

            Label location = new Label();
            location.Text = _dir;
            location.ForeColor = Color.FromArgb(152, 163, 183);
            location.Bounds = new Rectangle(32, 170, 456, 22);
            Controls.Add(location);

            _purgeBox = new CheckBox();
            _purgeBox.Text = "同时删除日程数据（data 目录，不可恢复）";
            _purgeBox.ForeColor = Color.FromArgb(55, 66, 88);
            _purgeBox.Bounds = new Rectangle(32, 204, 456, 24);
            Controls.Add(_purgeBox);

            _runBtn = new Button();
            _runBtn.Text = "卸载";
            _runBtn.Bounds = new Rectangle(304, 254, 184, 44);
            _runBtn.FlatStyle = FlatStyle.Flat;
            _runBtn.FlatAppearance.BorderSize = 0;
            _runBtn.BackColor = Color.FromArgb(240, 100, 100);
            _runBtn.ForeColor = Color.White;
            _runBtn.Font = new Font("Microsoft YaHei UI", 10F, FontStyle.Bold);
            _runBtn.Cursor = Cursors.Hand;
            _runBtn.Click += RunClick;
            Controls.Add(_runBtn);

            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Bounds = new Rectangle(210, 254, 84, 44);
            cancel.FlatStyle = FlatStyle.Flat;
            cancel.FlatAppearance.BorderColor = Color.FromArgb(214, 221, 233);
            cancel.FlatAppearance.BorderSize = 1;
            cancel.BackColor = Color.White;
            cancel.ForeColor = Color.FromArgb(58, 71, 97);
            cancel.Cursor = Cursors.Hand;
            cancel.Click += delegate { Close(); };
            Controls.Add(cancel);

            AcceptButton = _runBtn;
            ResumeLayout(false);
            PerformLayout();
        }

        private void PaintHeader(object sender, PaintEventArgs e)
        {
            Rectangle rect = new Rectangle(0, 0, 520, 88);
            using (LinearGradientBrush brush = new LinearGradientBrush(rect,
                Color.FromArgb(139, 92, 246), Color.FromArgb(69, 103, 242), LinearGradientMode.Horizontal))
            {
                e.Graphics.FillRectangle(brush, rect);
            }
            try
            {
                using (Icon icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath))
                {
                    if (icon != null) e.Graphics.DrawIcon(icon, new Rectangle(24, 24, 40, 40));
                }
            }
            catch (Exception) { }

            using (Font titleFont = new Font("Microsoft YaHei UI", 14F, FontStyle.Bold))
            using (Font subFont = new Font("Microsoft YaHei UI", 9F))
            using (SolidBrush white = new SolidBrush(Color.White))
            using (SolidBrush soft = new SolidBrush(Color.FromArgb(228, 234, 255)))
            {
                e.Graphics.DrawString("卸载 我的日程", titleFont, white, 78, 20);
                e.Graphics.DrawString("日程数据可选保留", subFont, soft, 80, 50);
            }
        }

        private void RunClick(object sender, EventArgs e)
        {
            bool purge = _purgeBox.Checked;
            _runBtn.Enabled = false;
            try
            {
                Remover.Run(_dir, purge);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "卸载过程中出现问题：" + ex.Message, AppInfo.Name,
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                _runBtn.Enabled = true;
                return;
            }
            MessageBox.Show(this,
                purge
                    ? "已卸载「我的日程」，程序与数据均已删除。"
                    : "已卸载「我的日程」。\r\n日程数据保留在：" + Path.Combine(_dir, "data"),
                AppInfo.Name, MessageBoxButtons.OK, MessageBoxIcon.Information);
            Close();
        }
    }
}
