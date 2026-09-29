param(
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [string]$TaskName='ClawCare-Standalone-Supervisor'
)
$ErrorActionPreference='Stop'
$PythonExe=[System.IO.Path]::GetFullPath($PythonExe)
$pythonw=Join-Path (Split-Path $PythonExe) 'pythonw.exe'
if(-not [System.IO.File]::Exists($pythonw)){throw 'pythonw.exe must exist beside PythonExe'}
$service=New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder=$service.GetFolder('\')
foreach($existing in $folder.GetTasks(0)){
    if($existing.Name -eq $TaskName){throw 'Task already exists; inspect it before changing the installation'}
}
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent()
$base=Join-Path $env:LOCALAPPDATA ('ClawCare\standalone-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
[void][System.IO.Directory]::CreateDirectory($base)
# Remove inherited access before creating the ledger. Only the local owner is granted access.
$acl=New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($identity.User)
$acl.SetAccessRuleProtection($true,$false)
$rule=New-Object System.Security.AccessControl.FileSystemAccessRule($identity.User,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
$acl.AddAccessRule($rule)
$directory=New-Object System.IO.DirectoryInfo($base)
$directory.SetAccessControl($acl)
$actual=$directory.GetAccessControl()
$rules=$actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])
if(-not $actual.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne $identity.User.Value){throw 'Private directory verification failed'}
foreach($name in @('clawcare.py','control.py','supervisor.py','process_lock.py')){
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $base $name)
}
$db=Join-Path $base 'clawcare.sqlite3'
& $PythonExe (Join-Path $base 'control.py') --db $db pause
if($LASTEXITCODE -ne 0){throw 'Failed to initialize a paused control plane'}
$task=$service.NewTask(0)
$task.RegistrationInfo.Description='Independent ClawCare monitoring supervisor; no autonomous repairs. Local-owner prototype.'
$task.Principal.UserId=$identity.Name
$task.Principal.LogonType=3
$task.Principal.RunLevel=0
$task.Settings.Enabled=$true
$task.Settings.AllowDemandStart=$true
$task.Settings.StartWhenAvailable=$true
$task.Settings.DisallowStartIfOnBatteries=$false
$task.Settings.StopIfGoingOnBatteries=$false
$task.Settings.ExecutionTimeLimit='PT0S'
$task.Settings.RestartCount=3
$task.Settings.RestartInterval='PT1M'
$task.Settings.MultipleInstances=2
$trigger=$task.Triggers.Create(9)
$trigger.UserId=$identity.Name
$trigger.Enabled=$true
$action=$task.Actions.Create(0)
$action.Path=$pythonw
$action.WorkingDirectory=$base
$action.Arguments='"'+(Join-Path $base 'supervisor.py')+'" --db "'+$db+'" run'
# CREATE only; never overwrite an existing scheduled task.
$registered=$folder.RegisterTaskDefinition($TaskName,$task,2,$identity.Name,$null,3,$null)
$receipt=[ordered]@{task=$TaskName;runtime=$base;database=$db;python=$PythonExe;startup='Current-user sign-in';repairs='Paused';targets=0}
$receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $base 'installation.json') -Encoding UTF8
[void]$registered.Run($null)
$receipt | ConvertTo-Json
