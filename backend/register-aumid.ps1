param(
    [Parameter(Mandatory = $true)][string]$AppId,
    [string]$DisplayName = 'MySchedule',
    [string]$IconPath = ''
)

# 在 HKCU 下注册 AppUserModelID，使系统通知可以显示为本应用
# （与开始菜单快捷方式注册互为备份，无需管理员权限）
$ErrorActionPreference = 'Stop'
try {
    $key = "HKCU:\SOFTWARE\Classes\AppUserModelId\$AppId"
    New-Item -Path $key -Force | Out-Null
    New-ItemProperty -Path $key -Name 'DisplayName' -Value $DisplayName -PropertyType String -Force | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($IconPath)) {
        New-ItemProperty -Path $key -Name 'IconUri' -Value $IconPath -PropertyType String -Force | Out-Null
    }
    New-ItemProperty -Path $key -Name 'ShowInSettings' -Value 1 -PropertyType DWord -Force | Out-Null
    Write-Output 'ok'
}
catch {
    Write-Output ('error: ' + $_.Exception.Message)
    exit 1
}
