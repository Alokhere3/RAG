<#
.SYNOPSIS
    Non-secret verification of .env permissions and Git tracking status.
.DESCRIPTION
    Validates:
    1. .env is ignored by Git and not tracked.
    2. Inspects volume filesystem type (FAT32 vs NTFS/ReFS).
    3. On NTFS volumes: verifies ACL does NOT grant broad access to 'Everyone'.
    4. Outputs only metadata without revealing any secret values.
#>
[CmdletBinding()]
param(
    [string]$EnvPath = "F:\RAG\.env",
    [string]$RepoRoot = "F:\RAG"
)

$ErrorCount = 0

Write-Host "=== F-01 .env Security Verification ==="

# 1. Verify Git Tracking
Write-Host "[1/3] Checking Git tracking status..."
$tracked = git -C $RepoRoot ls-files --error-unmatch $EnvPath 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[FAIL] .env file is tracked in Git!" -ForegroundColor Red
    $ErrorCount++
} else {
    Write-Host "[PASS] .env is NOT tracked in Git." -ForegroundColor Green
}

# 2. Verify .gitignore Coverage
Write-Host "[2/3] Checking .gitignore status..."
$checkIgnore = git -C $RepoRoot check-ignore $EnvPath 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] .env is properly ignored by Git rules." -ForegroundColor Green
} else {
    Write-Host "[FAIL] .env is NOT covered by .gitignore!" -ForegroundColor Red
    $ErrorCount++
}

# 3. Inspect Filesystem & ACL Permissions
Write-Host "[3/3] Inspecting volume filesystem and permissions on $EnvPath..."
if (Test-Path $EnvPath) {
    $driveLetter = (Split-Path (Resolve-Path $EnvPath) -Qualifier).TrimEnd(':')
    $vol = Get-Volume -DriveLetter $driveLetter -ErrorAction SilentlyContinue

    if ($vol -and $vol.FileSystemType -in @("FAT32", "FAT", "exFAT")) {
        Write-Host "[WARN] Host filesystem on drive ${driveLetter}: is $($vol.FileSystemType)." -ForegroundColor Yellow
        Write-Host "       $($vol.FileSystemType) does NOT support native NTFS Access Control Lists (ACLs)." -ForegroundColor Yellow
        Write-Host "       Windows returns synthetic Everyone:FullControl for all files on this volume." -ForegroundColor Yellow
        Write-Host "       [OPERATOR REQUIREMENT] For production/staging, repository must be hosted on an NTFS/ReFS/ext4 volume enforcing restricted ACLs." -ForegroundColor Yellow
    } else {
        $acl = Get-Acl -Path $EnvPath
        $insecurePrincipals = @("Everyone", "Authenticated Users")
        $foundInsecure = @()
        
        foreach ($access in $acl.Access) {
            $id = $access.IdentityReference.Value
            if ($access.AccessControlType -eq "Allow" -and $insecurePrincipals -contains $id) {
                $foundInsecure += $id
            }
        }
        
        if ($foundInsecure.Count -gt 0) {
            Write-Host "[FAIL] Insecure principals detected on NTFS volume with Allow permissions: $($foundInsecure -join ', ')" -ForegroundColor Red
            $ErrorCount++
        } else {
            Write-Host "[PASS] No broad public or unauthorized principals (Everyone / Authenticated Users) detected on NTFS volume." -ForegroundColor Green
        }
        
        Write-Host "Authorized Principals:"
        $acl.Access | Select-Object IdentityReference, FileSystemRights, AccessControlType | Format-Table -AutoSize | Out-String | Write-Host
    }
} else {
    Write-Warning "[WARN] Target .env file does not exist at $EnvPath"
}

if ($ErrorCount -eq 0) {
    Write-Host "[+] F-01 VERIFICATION COMPLETED (Source, tracking, and filesystem evaluated)." -ForegroundColor Green
    exit 0
} else {
    Write-Host "[-] F-01 VERIFICATION FAILED: $ErrorCount issue(s) detected." -ForegroundColor Red
    exit 1
}
