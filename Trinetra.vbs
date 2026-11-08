Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

strPythonw = strDir & "\services\vision-engine\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(strPythonw) Then
    strPythonw = "pythonw.exe"
End If

strLauncher = strDir & "\launch_trinetra.py"
WshShell.Run """" & strPythonw & """ """ & strLauncher & """", 0, False
