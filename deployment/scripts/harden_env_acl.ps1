<#
.SYNOPSIS
    Hardens NTFS Access Control List (ACL) on .env file.
.DESCRIPTION
    Removes insecure 'Everyone' grant and restricts access strictly to:
    - Current authenticated user (Owner)
    - BUILTIN\Administrators
    - NT AUTHORITY\SYSTEM
#>
[CmdletBinding()]
param(
    [string]$EnvPath = "F:\RAG\.env"
)

$target = (Resolve-Path -Path $EnvPath).Path
Write-Host "[*] Hardening ACL on: $target"

$acl = Get-Acl -Path $target

# Disable inheritance and remove existing inherited rules
$acl.SetAccessRuleProtection($true, $false)

# Clear existing access rules
$rules = @($acl.Access)
foreach ($r in $rules) {
    $acl.RemoveAccessRule($r) | Out-Null
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "[*] Setting exclusive access for: $currentUser, BUILTIN\Administrators, NT AUTHORITY\SYSTEM"

$ruleUser = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $currentUser,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$ruleAdmin = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Administrators",
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$ruleSystem = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "NT AUTHORITY\SYSTEM",
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)

$acl.AddAccessRule($ruleUser)
$acl.AddAccessRule($ruleAdmin)
$acl.AddAccessRule($ruleSystem)

Set-Acl -Path $target -AclObject $acl
Write-Host "[+] ACL hardening complete."
