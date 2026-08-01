# verify_release.ps1 - ASCII-only, safe for Windows PowerShell 5.1
# Run from the repo root with the venv activated
$pass = 0; $fail = 0
function Ok($m)  { $script:pass++; Write-Host "  [PASS] $m" -ForegroundColor Green }
function Bad($m) { $script:fail++; Write-Host "  [FAIL] $m" -ForegroundColor Red }
function Skip($m){ Write-Host "  [SKIP] $m" -ForegroundColor Yellow }

# Single source of truth for the version: pyproject.toml (avoids drift).
$version = (Select-String -Path "pyproject.toml" -Pattern '^version = "([^"]+)"').Matches.Groups[1].Value
if (-not $version) { Write-Host "Cannot read version from pyproject.toml" -ForegroundColor Red; exit 1 }

Write-Host "== 1. Entry points ==" -ForegroundColor Cyan
$ver = (pyai --version 2>&1 | Out-String).Trim()
if ($ver -match "pyai $([regex]::Escape($version))") { Ok "--version -> $ver" } else { Bad "--version -> '$ver'" }
py-ai --help 2>&1 | Out-Null;  if ($LASTEXITCODE -eq 0) { Ok "py-ai alias" } else { Bad "py-ai alias" }
python -m py_ai --help 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { Ok "python -m py_ai" } else { Bad "python -m py_ai" }
pip check 2>&1 | Out-Null;     if ($LASTEXITCODE -eq 0) { Ok "pip check" } else { Bad "pip check" }

Write-Host "== 2. Test suite ==" -ForegroundColor Cyan
pytest -q
if ($LASTEXITCODE -eq 0) { Ok "pytest suite" } else { Bad "pytest suite" }

Write-Host "== 3. CLI smoke on demo project ==" -ForegroundColor Cyan
$demo = Join-Path $env:TEMP ("pyai_check_" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force "$demo\sub" | Out-Null
Set-Content "$demo\app.py"      'print("hi")'    -Encoding ascii
Set-Content "$demo\.env"        'SECRET=hunter2' -Encoding ascii
Set-Content "$demo\.gitignore"  '*.log'          -Encoding ascii
Set-Content "$demo\debug.log"   'noise'          -Encoding ascii
$outFile = "$demo\ai_context.txt"

Push-Location $demo; pyai --no-clipboard | Out-Null; Pop-Location
$out = Get-Content $outFile -Raw

if ($out -match "Estimated tokens: ~") { Ok "token stats in header" } else { Bad "token stats" }
if ($out -match "Total lines:")        { Ok "line stats in header" } else { Bad "line stats" }
if ($out -like "*SECRET=hunter2*")     { Bad ".env LEAKED!" } else { Ok ".env never packed" }

python -c "import pathspec" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
  $content = ($out -split "FILES CONTENT")[1]
  if ($content -like "*debug.log*") { Bad ".gitignore not respected" } else { Ok ".gitignore (*.log) respected" }
} else { Skip "pathspec not installed - optional .gitignore check skipped" }

Push-Location $demo; pyai --no-clipboard | Out-Null; Pop-Location
$tree = ((Get-Content $outFile -Raw) -split "FILES CONTENT")[0]
if ($tree -like "*ai_context.txt*") { Bad "output file appears in tree" } else { Ok "output excludes itself (repeat run)" }

Write-Host "== 4. Clipboard (desktop path) ==" -ForegroundColor Cyan
Push-Location $demo; $clipLog = (pyai 2>&1 | Out-String); Pop-Location
if ($clipLog -like "*copied to clipboard successfully*") {
  $clip = Get-Clipboard
  if ($clip -like "*PROJECT CONTEXT PACK*") { Ok "clipboard success path" } else { Bad "clipboard content mismatch" }
} else { Bad "clipboard copy failed: $clipLog" }

Write-Host "== 5. Options and exit codes ==" -ForegroundColor Cyan
$demo2 = Join-Path $env:TEMP ("pyai_excl_" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force $demo2 | Out-Null
Set-Content "$demo2\app.py"  'print("hi")' -Encoding ascii
Set-Content "$demo2\keep.md" '# doc'       -Encoding ascii
pyai $demo2 --exclude "*.py" --no-clipboard -o "$demo2\out.txt" | Out-Null
if ((Get-Content "$demo2\out.txt" -Raw) -like "*START OF FILE: app.py*") { Bad "--exclude ignored" } else { Ok "--exclude works" }

Write-Host "== 6. Build and wheel ==" -ForegroundColor Cyan
pip install -q build twine 2>&1 | Out-Null
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
python -m build 2>&1 | Out-Null
if (($LASTEXITCODE -eq 0) -and (Test-Path "dist\*.whl")) { Ok "python -m build" } else { Bad "build" }
twine check dist\* 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok "twine check" } else { Bad "twine check" }

$wv = Join-Path $env:TEMP "pyai_wheel_venv"
python -m venv $wv 2>&1 | Out-Null
$whl = (Get-ChildItem dist\*.whl | Select-Object -First 1).FullName
& "$wv\Scripts\pip.exe" install -q $whl 2>&1 | Out-Null
$wvVer = (& "$wv\Scripts\pyai.exe" --version 2>&1 | Out-String).Trim()
if ($wvVer -match $([regex]::Escape($version))) { Ok "wheel smoke in fresh venv -> $wvVer" } else { Bad "wheel smoke: '$wvVer'" }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RESULT: $pass passed, $fail failed" -ForegroundColor Cyan
if ($fail -eq 0) { Write-Host "READY FOR RELEASE" -ForegroundColor Green; exit 0 } else { Write-Host "FIX ISSUES BEFORE RELEASE" -ForegroundColor Red; exit 1 }