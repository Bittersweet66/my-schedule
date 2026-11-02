' ============================================================
'  我的日程 · 静默启动器
'  双击即可启动应用（不显示黑色命令行窗口）
'
'  查找 Python 的顺序：
'    1. 安装版自带的 runtime\pythonw.exe
'    2. 系统 PATH 中的 pythonw.exe
' ============================================================
Option Explicit

Dim fso, shell, base, pyw, appPy, args, i, q, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
appPy = base & "\backend\app.py"
q = Chr(34)

If Not fso.FileExists(appPy) Then
  MsgBox "找不到程序文件：" & appPy, 16, "我的日程"
  WScript.Quit 1
End If

pyw = base & "\runtime\pythonw.exe"
If Not fso.FileExists(pyw) Then
  pyw = "pythonw.exe"
End If

args = ""
For i = 0 To WScript.Arguments.Count - 1
  args = args & " " & q & WScript.Arguments(i) & q
Next

cmd = q & pyw & q & " " & q & appPy & q & args
shell.CurrentDirectory = base

On Error Resume Next
shell.Run cmd, 0, False
If Err.Number <> 0 Then
  MsgBox "启动失败：没找到 Python。" & vbCrLf & vbCrLf & _
         "请先安装 Python 3（勾选 Add Python to PATH），" & vbCrLf & _
         "或使用安装包 / 便携版运行。", 16, "我的日程"
  WScript.Quit 1
End If
