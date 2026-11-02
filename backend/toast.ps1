param(
    [Parameter(Mandatory = $true)][string]$Path
)

# 显示 Windows 系统通知（Toast）。数据通过 UTF-8 JSON 文件传入，避免中文转义问题。
$ErrorActionPreference = 'Stop'
try {
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $data = $raw | ConvertFrom-Json

    $title = [string]$data.title
    $body = [string]$data.body
    $appId = [string]$data.appId
    if ([string]::IsNullOrWhiteSpace($appId)) {
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    }

    $actionLabel = [string]$data.actionLabel
    if ([string]::IsNullOrWhiteSpace($actionLabel)) {
        $actionLabel = 'Open'
    }

    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $toast = $xml.CreateElement('toast')
    $toast.SetAttribute('scenario', 'reminder')

    $visual = $xml.CreateElement('visual')
    $binding = $xml.CreateElement('binding')
    $binding.SetAttribute('template', 'ToastGeneric')

    $textTitle = $xml.CreateElement('text')
    $textTitle.InnerText = $title
    $textBody = $xml.CreateElement('text')
    $textBody.InnerText = $body

    [void]$binding.AppendChild($textTitle)
    [void]$binding.AppendChild($textBody)
    [void]$visual.AppendChild($binding)
    [void]$toast.AppendChild($visual)

    $actions = $xml.CreateElement('actions')
    $action = $xml.CreateElement('action')
    $action.SetAttribute('content', $actionLabel)
    $action.SetAttribute('arguments', 'open')
    $action.SetAttribute('activationType', 'foreground')
    [void]$actions.AppendChild($action)
    [void]$toast.AppendChild($actions)
    [void]$xml.AppendChild($toast)

    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId)
    $notification = New-Object Windows.UI.Notifications.ToastNotification $xml
    $notifier.Show($notification)
    Write-Output 'ok'
}
catch {
    Write-Output ('error: ' + $_.Exception.Message)
    exit 1
}
