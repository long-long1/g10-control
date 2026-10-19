$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$devices = @(Get-PnpDevice -PresentOnly | Where-Object {
    $_.Class -in @('Bluetooth','HIDClass','Keyboard','Mouse','AudioEndpoint','MEDIA')
})
$allProperties = Get-PnpDeviceProperty -InstanceId @($devices.InstanceId) -KeyName @('DEVPKEY_Device_HardwareIds','DEVPKEY_Device_ContainerId','DEVPKEY_Device_Parent','DEVPKEY_Device_BusReportedDeviceDesc') -ErrorAction SilentlyContinue
$rows = foreach ($device in $devices) {
    $properties = @{}
    $allProperties | Where-Object { $_.InstanceId -eq $device.InstanceId } |
        ForEach-Object { $properties[$_.KeyName] = $_.Data }
    [PSCustomObject]@{name=$device.FriendlyName; class=$device.Class; status=$device.Status;
        instance_id=$device.InstanceId; properties=$properties;
        capture_endpoint=($device.Class -eq 'AudioEndpoint' -and $device.InstanceId -match '\{0\.0\.1\.')}
}
ConvertTo-Json -InputObject @($rows) -Depth 8
