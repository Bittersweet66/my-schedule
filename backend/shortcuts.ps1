param(
    [Parameter(Mandatory = $true)][string]$LnkPath,
    [string]$TargetPath = '',
    [string]$Arguments = '',
    [string]$WorkingDirectory = '',
    [string]$IconLocation = '',
    [string]$AppId = '',
    [string]$Description = 'MySchedule',
    [switch]$Remove
)

# 创建 / 删除 Windows 快捷方式；可通过 AppId 参数写入 AppUserModelID，
# 让系统通知显示为本应用（名称 + 图标）。
$ErrorActionPreference = 'Stop'

if ($Remove) {
    if (Test-Path -LiteralPath $LnkPath) {
        Remove-Item -LiteralPath $LnkPath -Force
    }
    Write-Output 'removed'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($TargetPath)) {
    Write-Output 'error: TargetPath required'
    exit 1
}

$parent = Split-Path -Parent $LnkPath
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($LnkPath)
$lnk.TargetPath = $TargetPath
if ($Arguments) { $lnk.Arguments = $Arguments }
if ($WorkingDirectory) { $lnk.WorkingDirectory = $WorkingDirectory }
if ($IconLocation) { $lnk.IconLocation = $IconLocation }
$lnk.Description = $Description
$lnk.Save()

if ($AppId) {
    if (-not ('ShortcutAppId' -as [type])) {
        $source = @'
using System;
using System.Runtime.InteropServices;

public static class ShortcutAppId
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct PropertyKey
    {
        public Guid fmtid;
        public uint pid;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct PropVariant
    {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public IntPtr pointerValue;
    }

    [ComImport]
    [Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint cProps);
        void GetAt(uint iProp, out PropertyKey pkey);
        void GetValue(ref PropertyKey key, out PropVariant pv);
        void SetValue(ref PropertyKey key, ref PropVariant pv);
        void Commit();
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    private static extern void SHGetPropertyStoreFromParsingName(
        string path, IntPtr bindContext, uint flags, ref Guid riid, out IPropertyStore store);

    public static void Set(string shortcutPath, string appId)
    {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(shortcutPath, IntPtr.Zero, 2, ref iid, out store);
        try
        {
            PropVariant pv = new PropVariant();
            pv.vt = 31;
            pv.pointerValue = Marshal.StringToCoTaskMemUni(appId);
            try
            {
                PropertyKey key = new PropertyKey();
                key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
                key.pid = 5;
                store.SetValue(ref key, ref pv);
                store.Commit();
            }
            finally
            {
                Marshal.FreeCoTaskMem(pv.pointerValue);
            }
        }
        finally
        {
            Marshal.ReleaseComObject(store);
        }
    }
}
'@
        Add-Type -TypeDefinition $source
    }
    [ShortcutAppId]::Set($LnkPath, $AppId)
    Write-Output 'ok-with-appid'
}
else {
    Write-Output 'ok'
}
