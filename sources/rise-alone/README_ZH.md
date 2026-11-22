[English](README.md) | 简体中文

# RiseAloneTrainer 源码与构建

快照包含插件实现和 PowerShell 构建脚本。存档备份使用公开版的当前用户目录，完整构建需要匹配的游戏接口和四个派生索引。

使用带 Roslyn 程序集的 PowerShell 7。将 `$loader` 指向 BepInEx 6.0.0-be.793 的 Unity IL2CPP x64 根目录，`$interop` 指向该游戏生成的 interop 目录，`$indexes` 指向含有 `StoryClips.txt`、`ChoiceRisks.tsv`、`TaskKeys.tsv` 和 `ChoiceNames.tsv` 的本地目录。公开源码目录省略了游戏程序集和这四份原始索引。

```powershell
./Build.ps1 -LoaderRoot $loader -Interop $interop -IndexDirectory $indexes
```

用匹配的本地输入重建后，`release/RiseAlonePlugin.dll` 的 SHA-256 为 `b9db0b78287ef3b70c790b59e3d517115babde3be3f43725679cef4f2d8d8aa2`，与完整包内的插件逐字节一致。[项目说明](../../games/rise-alone/README_ZH.md)
