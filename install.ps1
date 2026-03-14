# Edict for OpenCode installer (Windows PowerShell)
# Usage:  irm https://raw.githubusercontent.com/CyberPunk-2022/edict-opencode/master/install.ps1 | iex
#   or:   .\install.ps1              (from local clone)
#
# Requirements: Developer Mode enabled -OR- run as Administrator (for symlinks)
#   Windows 10: Settings → Update & Security → For developers
#   Windows 11: Settings → System → For developers

$ErrorActionPreference = "Stop"

$installDir = "$env:USERPROFILE\.config\opencode\edict-opencode"
$pluginsDir = "$env:USERPROFILE\.config\opencode\plugins"
$skillsDir  = "$env:USERPROFILE\.config\opencode\skills"
$repoUrl    = "https://github.com/CyberPunk-2022/edict-opencode.git"

Write-Host "Installing edict-opencode for OpenCode..."

# Detect if running from local clone
$scriptDir = $null
try {
    $p = $MyInvocation.MyCommand.Path
    if ($p) { $scriptDir = Split-Path -Parent $p }
} catch { }
$isLocal = $false
if ($scriptDir) {
    $marker = Join-Path $scriptDir "agent_config.json"
    if (Test-Path $marker) { $isLocal = $true }
}

if ($isLocal) {
    # Local install: junction from config dir to current directory
    $sourceDir = $scriptDir
    if ((Resolve-Path $sourceDir).Path -ne (Resolve-Path $installDir -ErrorAction SilentlyContinue).Path) {
        New-Item -ItemType Directory -Force -Path (Split-Path $installDir) | Out-Null
        if (Test-Path $installDir) { Remove-Item $installDir -Force -Recurse }
        New-Item -ItemType Junction -Path $installDir -Target $sourceDir | Out-Null
        Write-Host "  -> Linked $installDir -> $sourceDir"
    }
} else {
    # Remote install: clone or update
    if (Test-Path (Join-Path $installDir ".git")) {
        Write-Host "  -> Updating existing installation..."
        git -C $installDir pull --ff-only
    } else {
        Write-Host "  -> Cloning repository..."
        git clone $repoUrl $installDir
    }
    $sourceDir = $installDir
}

# Create directories
New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null
New-Item -ItemType Directory -Force -Path $skillsDir  | Out-Null

# Remove stale links / old copies
$pluginLink = Join-Path $pluginsDir "edict.js"
$skillLink  = Join-Path $skillsDir  "edict"
if (Test-Path $pluginLink) { Remove-Item $pluginLink -Force }
if (Test-Path $skillLink)  { Remove-Item $skillLink  -Force -Recurse }

# Plugin: SymbolicLink (requires Developer Mode or Admin)
New-Item -ItemType SymbolicLink `
    -Path   $pluginLink `
    -Target (Join-Path $sourceDir ".opencode\plugins\edict.js") | Out-Null

# Skills: Junction (works without special privileges)
New-Item -ItemType Junction `
    -Path   $skillLink `
    -Target (Join-Path $sourceDir "skills") | Out-Null

$versionFile = Join-Path $sourceDir "VERSION"
$version = if (Test-Path $versionFile) { (Get-Content $versionFile -Raw).Trim() } else { "unknown" }

Write-Host ""
Write-Host "Done! edict-opencode v$version installed."
Write-Host ""
Write-Host "  Version: $version"
Write-Host "  Plugin : $pluginLink"
Write-Host "  Skills : $skillLink"
Write-Host ""
Write-Host "Restart OpenCode to activate."
Write-Host ""
Write-Host "First time? Initialize a project:"
Write-Host "  python `"$sourceDir\scripts\edict_tasks_init.py`" --path <your-project>"
Write-Host ""
Write-Host "  (Existing .edict/edict-tasks.json will NOT be overwritten unless you pass --force)"
