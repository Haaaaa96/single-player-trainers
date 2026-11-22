English | [简体中文](README_ZH.md)

# RiseAloneTrainer · Source and build

This snapshot includes the plugin and its PowerShell build script. Save backups use the current user's local application data directory. The build requires matching game interfaces and four derived lookup files.

Use PowerShell 7 with its bundled Roslyn assemblies. Set `$loader` to the root of BepInEx 6.0.0-be.793 for Unity IL2CPP x64, `$interop` to the matching generated game interfaces, and `$indexes` to a local directory containing `StoryClips.txt`, `ChoiceRisks.tsv`, `TaskKeys.tsv` and `ChoiceNames.tsv`. Game assemblies and raw lookup files are omitted from the public tree.

```powershell
./Build.ps1 -LoaderRoot $loader -Interop $interop -IndexDirectory $indexes
```

With matching local inputs this build produced `release/RiseAlonePlugin.dll` with SHA-256 `b9db0b78287ef3b70c790b59e3d517115babde3be3f43725679cef4f2d8d8aa2`, identical to the release payload. [Project overview](../../games/rise-alone/README.md)
