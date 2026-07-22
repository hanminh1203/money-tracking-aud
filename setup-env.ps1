#Requires -Version 5.1
<#
.SYNOPSIS
  Interactive .env setup for backend (and frontend when it has secrets).

.NOTES
  When adding a new secret to the project, update:
  - backend/.env.example and/or frontend/.env.example
  - The $BackendSecrets / $FrontendSecrets lists in this script
  See .cursor/rules/env-setup-script.mdc
#>

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Read-SecretValue {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$Prompt,
    [string]$Current = '',
    [string]$Default = '',
    [switch]$GenerateIfEmpty,
    [switch]$AllowEmpty
  )

  $hint = if ($Current) {
    $masked = if ($Current.Length -le 8) { '********' } else { $Current.Substring(0, 4) + '…' + $Current.Substring($Current.Length - 4) }
    " [current: $masked; Enter keeps]"
  } elseif ($Default) {
    " [default: $Default]"
  } elseif ($GenerateIfEmpty) {
    ' [Enter = auto-generate]'
  } else {
    ''
  }

  $input = Read-Host "$Prompt$hint"
  if ([string]::IsNullOrWhiteSpace($input)) {
    if ($Current) { return $Current }
    if ($GenerateIfEmpty) {
      $bytes = New-Object byte[] 48
      [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
      return ([Convert]::ToBase64String($bytes) -replace '[^a-zA-Z0-9]', 'x')
    }
    if ($Default) { return $Default }
    if ($AllowEmpty) { return '' }
    Write-Host "  Value required for $Name." -ForegroundColor Yellow
    return Read-SecretValue @PSBoundParameters
  }
  return $input.Trim()
}

function Read-EnvFile {
  param([string]$Path)
  $map = @{}
  if (-not (Test-Path $Path)) { return $map }
  Get-Content $Path | ForEach-Object {
    $line = $_.TrimEnd()
    if ($line -match '^\s*#' -or $line -match '^\s*$') { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    $k = $line.Substring(0, $eq).Trim()
    $v = $line.Substring($eq + 1)
    $map[$k] = $v
  }
  return $map
}

function Write-EnvFromExample {
  param(
    [Parameter(Mandatory)][string]$ExamplePath,
    [Parameter(Mandatory)][string]$OutPath,
    [Parameter(Mandatory)][hashtable]$Values
  )
  if (-not (Test-Path $ExamplePath)) {
    throw "Missing example file: $ExamplePath"
  }
  $out = @()
  Get-Content $ExamplePath | ForEach-Object {
    $line = $_
    if ($line -match '^\s*#' -or $line -match '^\s*$') {
      $out += $line
      return
    }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) {
      $out += $line
      return
    }
    $k = $line.Substring(0, $eq).Trim()
    if ($Values.ContainsKey($k)) {
      $out += "$k=$($Values[$k])"
    } else {
      $out += $line
    }
  }
  $dir = Split-Path -Parent $OutPath
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
  Set-Content -Path $OutPath -Value $out -Encoding utf8
}

Write-Host ''
Write-Host '=== Finance Dashboard .env setup ===' -ForegroundColor Cyan
Write-Host 'Press Enter to keep an existing value or accept a default.'
Write-Host ''

# ---------------------------------------------------------------------------
# Backend secrets (prompted) + defaults from .env.example for the rest
# ---------------------------------------------------------------------------
# KEEP IN SYNC with backend/.env.example — see .cursor/rules/env-setup-script.mdc
$BackendSecrets = @(
  @{ Name = 'DJANGO_SECRET_KEY'; Prompt = 'Django secret key (session/CSRF signing)'; GenerateIfEmpty = $true }
  @{ Name = 'GOOGLE_CLIENT_ID'; Prompt = 'Google OAuth Client ID' }
  @{ Name = 'GOOGLE_CLIENT_SECRET'; Prompt = 'Google OAuth Client Secret' }
  @{ Name = 'SHEET_ID'; Prompt = 'Google Spreadsheet ID (from /d/<id>/edit URL)' }
  @{ Name = 'GROQ_API_KEY'; Prompt = 'Groq API key (assistant + receipt OCR)' }
)

$BackendDefaults = @{
  DJANGO_DEBUG              = 'true'
  ALLOWED_HOSTS             = 'localhost,127.0.0.1,.vercel.app'
  CSRF_TRUSTED_ORIGINS      = 'http://localhost:5173,http://127.0.0.1:5173'
  GOOGLE_REDIRECT_URI       = 'http://localhost:5173/api/auth/google/callback'
  FRONTEND_URL              = 'http://localhost:5173'
  POSTGRES_HOST             = '127.0.0.1'
  POSTGRES_PORT             = '5432'
  POSTGRES_DB               = 'finance'
  POSTGRES_USER             = 'finance'
  POSTGRES_PASSWORD         = 'finance'
  TRANSACTIONS_TABLE        = 'Transactions'
  CATEGORY_TABLE            = 'Category'
  SOURCES_TABLE             = 'Sources'
  RECEIPT_TABLE             = 'Receipt'
  RECEIPT_ITEMS_TABLE       = 'Receipt_Items'
  GIFTCARD_TABLE            = 'Giftcard'
  GROQ_MODEL                = 'llama-3.3-70b-versatile'
  GROQ_VISION_MODEL         = 'qwen/qwen3.6-27b'
}

# Frontend secrets — currently none (SPA has no VITE_* secrets).
# When adding one: put it in frontend/.env.example AND append here.
$FrontendSecrets = @()

$backendExample = Join-Path $Root 'backend\.env.example'
$backendEnv = Join-Path $Root 'backend\.env'
$frontendExample = Join-Path $Root 'frontend\.env.example'
$frontendEnv = Join-Path $Root 'frontend\.env'

$existingBackend = Read-EnvFile $backendEnv
$backendValues = @{}

Write-Host '--- Backend (backend/.env) ---' -ForegroundColor Green
foreach ($s in $BackendSecrets) {
  $params = @{
    Name            = $s.Name
    Prompt          = $s.Prompt
    Current         = $(if ($existingBackend.ContainsKey($s.Name)) { $existingBackend[$s.Name] } else { '' })
    GenerateIfEmpty = [bool]$s.GenerateIfEmpty
  }
  $backendValues[$s.Name] = Read-SecretValue @params
}

foreach ($k in $BackendDefaults.Keys) {
  if ($existingBackend.ContainsKey($k) -and $existingBackend[$k]) {
    $backendValues[$k] = $existingBackend[$k]
  } else {
    $backendValues[$k] = $BackendDefaults[$k]
  }
}

# Preserve any extra keys already in .env that we don't manage
foreach ($k in $existingBackend.Keys) {
  if (-not $backendValues.ContainsKey($k)) {
    $backendValues[$k] = $existingBackend[$k]
  }
}

Write-EnvFromExample -ExamplePath $backendExample -OutPath $backendEnv -Values $backendValues
Write-Host "Wrote $backendEnv" -ForegroundColor Green

Write-Host ''
Write-Host '--- Frontend (frontend/.env) ---' -ForegroundColor Green
$existingFrontend = Read-EnvFile $frontendEnv
$frontendValues = @{}

if ($FrontendSecrets.Count -eq 0) {
  Write-Host 'No frontend secrets required (API secrets live on the backend).'
  if (-not (Test-Path $frontendEnv)) {
    Copy-Item $frontendExample $frontendEnv
    Write-Host "Wrote $frontendEnv from .env.example" -ForegroundColor Green
  } else {
    Write-Host "Left existing $frontendEnv unchanged."
  }
} else {
  foreach ($s in $FrontendSecrets) {
    $params = @{
      Name    = $s.Name
      Prompt  = $s.Prompt
      Current = $(if ($existingFrontend.ContainsKey($s.Name)) { $existingFrontend[$s.Name] } else { '' })
      Default = $(if ($s.Default) { $s.Default } else { '' })
    }
    $frontendValues[$s.Name] = Read-SecretValue @params
  }
  foreach ($k in $existingFrontend.Keys) {
    if (-not $frontendValues.ContainsKey($k)) {
      $frontendValues[$k] = $existingFrontend[$k]
    }
  }
  Write-EnvFromExample -ExamplePath $frontendExample -OutPath $frontendEnv -Values $frontendValues
  Write-Host "Wrote $frontendEnv" -ForegroundColor Green
}

Write-Host ''
Write-Host 'Done. You can run start.bat next.' -ForegroundColor Cyan
Write-Host ''
