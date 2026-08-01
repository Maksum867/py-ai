# verify_all.ps1 - one-file full verification for py-for-ai (py-ai)
#
# Runs EVERYTHING needed before publishing:
#   0. Environment checks
#   1. Install (pip upgrade + editable install with [dev])
#   2. Test suite (pytest) + compileall (+ ruff if available)
#   3. CLI smoke tests (packing, filters, gitignore, exit codes)
#   4. Git hygiene
#   5. Build (wheel + sdist) + twine check
#   6. Wheel smoke test in a clean temporary venv + pip check
#
# Usage (from the repo root, venv active is recommended):
#   powershell -ExecutionPolicy Bypass -File verify_all.ps1
#   .\verify_all.ps1                (PowerShell)
#   .\verify_all.ps1 -SkipBuild     (skip build/wheel steps for a fast check)
#
# Exit code: 0 = all checks passed, 1 = at least one FAIL.
# Compatible with Windows PowerShell 5.1 (ASCII-only, no && / ?? / ternary).

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

$pass = 0; $fail = 0; $warn = 0

function Ok($m)  { $script:pass++; Write-Host "  [PASS] $m" -ForegroundColor Green }
function Bad($m) { $script:fail++; Write-Host "  [FAIL] $m" -ForegroundColor Red }
function Warn($m){ $script:warn++; Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Check($cond, $msg) { if ($cond) { Ok $msg } else { Bad $msg } }

# Run 'python -m <module> <params>' and return the exit code.
function Py([string]$module, [string[]]$params) {
    & python -m $module @params 2>&1 | Out-Null
    return $LASTEXITCODE
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " py-for-ai full verification" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# ---------------------------------------------------------------- 0. Environment
Write-Host "`n== 0. Environment ==" -ForegroundColor Cyan

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pyCmd) {
    Write-Host "  python not found on PATH. Cannot continue." -ForegroundColor Red
    exit 1
}
Ok "python available: $($pyCmd.Source)"
Write-Host "       $(python --version 2>&1)"

if ($env:VIRTUAL_ENV) { Ok "virtualenv active: $env:VIRTUAL_ENV" }
else { Warn "no active virtualenv - using the default interpreter" }

$code = Py "py_ai" @("--version")
Check ($code -eq 0) "py_ai importable (python -m py_ai --version)"

# optional extras presence
python -c "import tiktoken, pathspec" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok "optional deps present: tiktoken + pathspec" }
else { Warn "optional deps missing (heuristic token count, no .gitignore support)" }

# ---------------------------------------------------------------- 1. Install
Write-Host "`n== 1. Install ==" -ForegroundColor Cyan

$code = Py "pip" @("install", "-U", "-q", "pip")
Check ($code -eq 0) "pip upgraded"

$code = Py "pip" @("install", "-q", "-e", ".[dev]")
Check ($code -eq 0) "package installed editable with [dev]"

# ---------------------------------------------------------------- 2. Tests
Write-Host "`n== 2. Tests ==" -ForegroundColor Cyan

$code = Py "pytest" @("-q")
Check ($code -eq 0) "pytest suite passed (skips are OK)"

$code = Py "compileall" @("-q", "src", "tests")
Check ($code -eq 0) "compileall src tests"

$code = Py "ruff" @("--version")
if ($code -eq 0) {
    & python -m ruff check src tests
    $code = $LASTEXITCODE
    if ($code -eq 0) { Ok "ruff check src tests" }
    else { Bad "ruff check src tests (see details above); try: python -m ruff check src tests --fix" }
} else {
    Warn "ruff not installed - lint step skipped (pip install ruff to enable)"
}

# ---------------------------------------------------------------- 3. CLI smoke
Write-Host "`n== 3. CLI smoke ==" -ForegroundColor Cyan

$demo = Join-Path $env:TEMP ("pyai_verify_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force "$demo\sub" | Out-Null
Set-Content "$demo\app.py"          'print("hi")'     -Encoding ascii
Set-Content "$demo\.env"            'SECRET=hunter2'  -Encoding ascii
Set-Content "$demo\.gitignore"      '*.log'           -Encoding ascii
Set-Content "$demo\debug.log"       'noise'           -Encoding ascii
Set-Content "$demo\sub\.gitignore"  '*.tmp'           -Encoding ascii
Set-Content "$demo\sub\secret.tmp"  'tmp'             -Encoding ascii
[IO.File]::WriteAllBytes((Join-Path $demo "dump.bin"), [byte[]](0, 1, 2, 3))

$verOut = (python -m py_ai --version 2>&1 | Out-String).Trim()
Check ($verOut -match "0\.2\.0") "pyai --version -> $verOut"

Push-Location $demo
python -m py_ai . --no-clipboard -o ctx.txt 2>&1 | Out-Null
$code1 = $LASTEXITCODE
Pop-Location
Check ($code1 -eq 0) "pack run exits 0"

$out = Get-Content (Join-Path $demo "ctx.txt") -Raw
Check ($out -like "*START OF FILE: app.py ---*")              "app.py packed"
Check ($out -notlike "*SECRET=hunter2*")                      ".env not packed (no secret leak)"
Check ($out -notlike "*START OF FILE: debug.log*")            ".gitignore '*.log' respected"
Check ($out -notlike "*START OF FILE: sub/secret.tmp*")       "nested .gitignore respected"
Check ($out -notlike "*START OF FILE: dump.bin*")             "binary file skipped"
Check ($out -like "*START OF FILE: .gitignore ---*")          "allowlisted .gitignore packed"

Push-Location $demo
python -m py_ai . --no-clipboard -o ctx2.txt 2>&1 | Out-Null
$code2 = $LASTEXITCODE
Pop-Location
Check ($code2 -eq 0) "second pack run exits 0"
$out2 = Get-Content (Join-Path $demo "ctx2.txt") -Raw
Check ($out2 -notlike "*START OF FILE: ai_context.txt*")      "leftover ai_context.txt not re-packed"

Push-Location $demo
python -m py_ai . --no-clipboard --no-gitignore -o ctx3.txt 2>&1 | Out-Null
Pop-Location
$out3 = Get-Content (Join-Path $demo "ctx3.txt") -Raw
Check ($out3 -like "*START OF FILE: debug.log*")              "--no-gitignore re-packs *.log"

# new feature flags (group 1)
Push-Location $demo
python -m py_ai . --no-clipboard --no-tree -o ctx4.txt 2>&1 | Out-Null
Pop-Location
$out4 = Get-Content (Join-Path $demo "ctx4.txt") -Raw
Check ($out4 -notlike "*DIRECTORY TREE*")                     "--no-tree omits the tree section"
Check ($out4 -like "*START OF FILE: app.py ---*")             "  ...but content still packed"

Push-Location $demo
python -m py_ai . --no-clipboard --no-token-count -o ctx5.txt 2>&1 | Out-Null
Pop-Location
$out5 = Get-Content (Join-Path $demo "ctx5.txt") -Raw
Check ($out5 -like "*Estimated tokens: disabled*")            "--no-token-count disables estimation"

Push-Location $demo
$quietOut = (python -m py_ai . --no-clipboard --quiet -o ctx6.txt 2>&1 | Out-String).Trim()
Pop-Location
Check ($quietOut -eq "")                                      "--quiet prints nothing on stdout"
Check (Test-Path (Join-Path $demo "ctx6.txt"))                "  ...but still writes the output file"

# exit codes
Push-Location $demo
python -m py_ai C:\nonexistent_dir_xyz 2>&1 | Out-Null; $e1 = $LASTEXITCODE
python -m py_ai . --max-file-size 0 2>&1 | Out-Null;      $e2 = $LASTEXITCODE
python -m py_ai . --format bogus 2>&1 | Out-Null;         $e3 = $LASTEXITCODE
Pop-Location
Check ($e1 -eq 1) "missing dir exits 1 (got $e1)"
Check ($e2 -eq 2) "max-file-size 0 exits 2 (got $e2)"
Check ($e3 -eq 2) "invalid --format exits 2 (got $e3)"

Remove-Item -Recurse -Force $demo -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- 4. Git hygiene
Write-Host "`n== 4. Git hygiene ==" -ForegroundColor Cyan

if (Test-Path ".git") {
    $junk = git ls-files | Select-String -Pattern "__pycache__|\.idea|\.pyc$|\.pytest_cache"
    if ($null -ne $junk) {
        Bad "no junk tracked (.idea/ __pycache__/ *.pyc)"
        Write-Host "       HINT: run  git rm -r --cached .idea src/py_ai/__pycache__  then  git add -A  and  git commit" -ForegroundColor Yellow
    } else {
        Ok "no junk tracked (.idea/ __pycache__/ *.pyc)"
    }
    $status = git status --porcelain
    if ($status) { Warn "uncommitted changes present (commit before publishing)" }
    else { Ok "git status clean" }
} else {
    Warn "not a git repository - skipping git checks"
}

# ---------------------------------------------------------------- 5-6. Build & wheel
if (-not $SkipBuild) {
    Write-Host "`n== 5. Build ==" -ForegroundColor Cyan

    $code = Py "pip" @("install", "-q", "build", "twine")
    Check ($code -eq 0) "build/twine installed"

    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    $code = Py "build" @()
    Check (($code -eq 0) -and (Test-Path "dist")) "python -m build succeeded"

    $whl   = Get-ChildItem "dist\*.whl"     | Select-Object -First 1
    $sdist = Get-ChildItem "dist\*.tar.gz"  | Select-Object -First 1
    Check (($null -ne $whl) -and ($null -ne $sdist)) "wheel + sdist produced"

    $code = Py "twine" @("check", "dist/*")
    Check ($code -eq 0) "twine check dist/*"

    Write-Host "`n== 6. Wheel smoke (clean venv) ==" -ForegroundColor Cyan
    $wv = Join-Path $env:TEMP ("pyai_wheel_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    $code = Py "venv" @($wv)
    Check ($code -eq 0) "temp venv created"

    $wvPy = Join-Path $wv "Scripts\python.exe"
    if (Test-Path $wvPy) {
        & $wvPy -m pip install -q $whl.FullName 2>&1 | Out-Null
        Check ($LASTEXITCODE -eq 0) "wheel installs in clean venv"
        $wvVer = (& $wvPy -m py_ai --version 2>&1 | Out-String).Trim()
        Check ($wvVer -match "0\.2\.0") "installed pyai --version -> $wvVer"
        & $wvPy -m pip check 2>&1 | Out-Null
        Check ($LASTEXITCODE -eq 0) "pip check in wheel venv"
    } else {
        Bad "temp venv python not found"
    }
    Remove-Item -Recurse -Force $wv -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------- Summary
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "RESULT: $pass passed, $fail failed, $warn warnings" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
if ($fail -eq 0) {
    Write-Host "ALL CHECKS PASSED - ready to publish" -ForegroundColor Green
    exit 0
} else {
    Write-Host "FIX THE FAILURES BEFORE PUBLISHING" -ForegroundColor Red
    exit 1
}
