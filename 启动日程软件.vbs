' ============================================================
'  我的日程 · 静默启动器
'  双击运行即可启动应用（不显示黑色命令行窗口）
'  安装版会优先使用随包附带的 runtime\pythonw.exe，
'  开发目录则回退到本机已安装的 Python。
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

' 1) 安装版：随包附带的运行时
pyw = base & "\runtime\pythonw.exe"
' 2) 开发版：本机 Python
If Not fso.FileExists(pyw) Then
  pyw = "C:\Users\yaoyikun\AppData\Local\Programs\Python\Python311\pythonw.exe"
End If
' 3) 最后退回 PATH
If Not fso.FileExists(pyw) Then
  pyw = "pythonw.exe"
End If

args = ""
For i = 0 To WScript.Arguments.Count - 1
  args = args & " " & q & WScript.Arguments(i) & q
Next

cmd = q & pyw & q & " " & q & appPy & q & args
shell.CurrentDirectory = base
' 用正常窗口样式启动：pythonw 本身没有控制台不会闪窗，
' 但隐藏样式会被子进程（浏览器）继承，导致应用窗口不可见
shell.Run cmd, 1, False
