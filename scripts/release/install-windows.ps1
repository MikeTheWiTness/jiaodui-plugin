$ErrorActionPreference = 'Stop'
$releaseRoot = $PSScriptRoot

$wheels = @(Get-ChildItem -LiteralPath $releaseRoot -Filter 'jiaodui-*-py3-none-any.whl' -File)
if ($wheels.Count -ne 1) {
    throw '发布目录必须且只能包含一个 jiaodui-*-py3-none-any.whl。'
}
$match = [regex]::Match($wheels[0].Name, '^jiaodui-(.+)-py3-none-any\.whl$')
if (-not $match.Success) {
    throw "无法从 wheel 文件名读取版本：$($wheels[0].Name)"
}
$version = $match.Groups[1].Value
$bundleManifestPath = Join-Path $releaseRoot 'dsh-jiaodui/package.json'
$bundleVersion = (Get-Content -LiteralPath $bundleManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json).version
if ($version -ne $bundleVersion) {
    throw "CLI wheel 与 DSH bundle 版本不一致：$version / $bundleVersion"
}

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    throw '未找到 Python Launcher。请先安装独立 CPython 3.12，并确认 py -3.12 可用。'
}
$pythonExe = & $pythonLauncher.Source -3.12 -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0 -or -not $pythonExe) {
    throw '未找到独立 CPython 3.12；请通过 python.org 安装后重试。'
}
$pythonVersion = & $pythonExe -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.12') {
    throw "要求 CPython 3.12，当前解释器版本为：$pythonVersion"
}

$pandoc = Get-Command pandoc -ErrorAction SilentlyContinue
if (-not $pandoc) {
    throw '未找到 Pandoc。请按 https://pandoc.org/installing.html 安装后重试。'
}
& $pandoc.Source --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Pandoc 不可执行：$($pandoc.Source)"
}

$constraints = Join-Path $releaseRoot 'runtime-constraints.txt'
if (-not (Test-Path -LiteralPath $constraints -PathType Leaf)) {
    throw "缺少运行依赖约束：$constraints"
}
$checksumManifest = Join-Path $releaseRoot 'SHA256SUMS'
foreach ($line in Get-Content -LiteralPath $checksumManifest -Encoding UTF8) {
    if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
        throw "SHA256SUMS 条目格式无效：$line"
    }
    $expectedHash = $Matches[1].ToLower()
    $relativePath = $Matches[2].Replace('/', [IO.Path]::DirectorySeparatorChar)
    $filePath = Join-Path $releaseRoot $relativePath
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "发布文件缺失：$relativePath"
    }
    $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $expectedHash) {
        throw "发布文件 SHA-256 不匹配：$relativePath"
    }
}
if (-not $env:LOCALAPPDATA) {
    throw '当前用户缺少 LOCALAPPDATA，无法确定安全的用户级 CLI 安装目录。'
}
$venv = Join-Path $env:LOCALAPPDATA "JiaoDuiAgentSkill/versions/$version/venv"
$venvPython = Join-Path $venv 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $venv) -Force | Out-Null
    & $pythonExe -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw '创建独立 jiaodui 虚拟环境失败。'
    }
}
$cli = Join-Path $venv 'Scripts/jiaodui.exe'
$wheel = "$($wheels[0].FullName)[render]"
& $venvPython -m pip install --force-reinstall --constraint $constraints $wheel
if ($LASTEXITCODE -ne 0) {
    throw '安装 jiaodui wheel 或受约束依赖失败。'
}
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) {
    throw 'Python 依赖存在冲突；CLI 尚未完成安装验收。'
}
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "安装后未找到 CLI：$cli"
}
$checkOutput = & $cli check-env --json
if ($LASTEXITCODE -ne 0) {
    throw "jiaodui check-env 未通过：`n$checkOutput"
}
$check = $checkOutput | ConvertFrom-Json
if (-not $check.ok) {
    throw "jiaodui check-env 未通过：`n$checkOutput"
}
$checkOutput
Write-Host "`nCLI 已安装并通过 check-env：$cli"
Write-Host "请通过 DSH 官方 install_bundle 安装：$(Join-Path $releaseRoot 'dsh-jiaodui')"
Write-Host '插件会按 bundle 版本自动发现该 CLI；如需覆盖，可在插件配置中设置 command。'
