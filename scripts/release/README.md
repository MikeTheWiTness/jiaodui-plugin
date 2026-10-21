# JiaoDuiAgentSkill final plugin release

This archive contains the matching DSH bundles and Python CLI wheel. It does not contain the Python interpreter or Pandoc; install independent CPython 3.12 and Pandoc before running the platform installer. Python dependencies are pinned in `runtime-constraints.txt` and are downloaded from the configured package index during installation.

The archive ships one bundle per landed subject:

- `dsh-jiaodui` — high-school physics preset（校对）
- `dsh-jiaodui-chemistry` — high-school chemistry preset（校对（高中化学））

They are independent: install one, the other, or both. Both share the same Python CLI and the same subject-agnostic native tool module; installing either one installs the CLI once.

## Verify and install

macOS:

```bash
shasum -a 256 -c dsh-jiaodui-0.1.0.tar.gz.sha256
tar -xzf dsh-jiaodui-0.1.0.tar.gz
cd JiaoDuiAgentSkill-0.1.0
bash install-macos.sh
```

Windows 11 PowerShell:

```powershell
$expected = (Get-Content .\\dsh-jiaodui-0.1.0.tar.gz.sha256 -Raw).Split()[0].ToLower()
$actual = (Get-FileHash .\\dsh-jiaodui-0.1.0.tar.gz -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) { throw '发布包 SHA-256 不匹配' }
New-Item -ItemType Directory .\\release -Force | Out-Null
tar -xzf .\\dsh-jiaodui-0.1.0.tar.gz -C .\\release
cd .\\release\\JiaoDuiAgentSkill-0.1.0
.\\install-windows.ps1
```

Install the extracted bundle directory through the DSH plugin page or `plugin_manager` with `action: install_bundle` (`dsh-jiaodui` and/or `dsh-jiaodui-chemistry`). The installer places the CLI in the versioned user data directory. Each bundle discovers that matching CLI by its own version; no shell PATH or developer checkout is required.

If PowerShell blocks local scripts, run this signed-off local script once with `powershell -ExecutionPolicy Bypass -File .\\install-windows.ps1`. The installer does not change the machine execution policy or edit DSH profile files.

The `SHA256SUMS` file inside the archive covers every released file. The `.tar.gz.sha256` sidecar covers the entire archive.
