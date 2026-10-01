# 构建 WulinToyBox / HaxxToyBox 1.1.0

[English](BUILD.md) | 简体中文

本目录用于个人研究归档。本次导出没有构建、运行测试、启动游戏或进行实机验证，也没有重新构建既有发行文件。

## 前置条件

- Windows x64、PowerShell 7，且 `$PSHOME` 内有 `Microsoft.CodeAnalysis.dll` 和 `Microsoft.CodeAnalysis.CSharp.dll`。
- 本机安装的《大侠立志传》，使用 `WulinSH` 目录布局。
- 已有匹配的 BepInEx IL2CPP 环境，包含 `dotnet`、`BepInEx/core`、已生成的 `BepInEx/interop`，以及 `BepInEx/plugins/HaxxToyBox/UniverseLib.IL2CPP.dll`。

既有游戏参考为 V1.2.0818 75、Steam build 24794582；历史环境使用 BepInEx 6.0.0-be.672 和 .NET Runtime 6.0.7。脚本引用已安装程序集，不下载前置、不生成 interop，也不安装整套环境。其它组合未验证。本目录不包含游戏／Unity DLL、加载器、运行库、生成缓存或其它 MOD。

## 构建

在本目录中使用 PowerShell 7：

```powershell
./build.ps1 -GameDir 'X:/Games/WulinSH'
```

示例路径须替换为本机实际安装目录；也可设置 `WULIN_GAME_DIR`。输出为 `build/HaxxToyBox.dll`。脚本将上游 `src/Assets/toybox` 作为资源编入 DLL，编译 C# 源码并打印 SHA-256，不安装或启动插件。

本次将游戏目录默认值通用化，并为相对已核实上游确有改动的 C# 文件添加中性变更注释；清单见 `NOTICE.txt`。产品源码来自提交 `f7a4f7b2d21fd8dbfcdd1b1a0ad09960c734da2d`，可执行语句未变；加注释后的公开副本不再与历史源码逐字节一致，不宣称可复建出相同哈希。

## 可用离线检查

```powershell
pwsh -NoProfile -File ./tests/check-item-search.ps1
```

该检查仅覆盖搜索文字辅助方法，不加载游戏，不代替界面或存档验证。本次导出未运行。

## 来源与权利

HaxxToyBox 来源为 Haxx 的 [neeetman/WuLinToyBoxMod](https://github.com/neeetman/WuLinToyBoxMod/tree/b2aee7a4be4c1254910ca1f13897d40853a5f20e)。须保留 `LICENSE.txt`、`NOTICE.txt` 及上游版权原文。`src/Assets/toybox` 与对应上游资源逐字节一致，SHA-256 为 `746dada617bdb07933f77c79a7110156e232e4acc4af5c0ebf9e9c6ebd11eaf8`。

HaxxToyBox 的 Apache-2.0 许可不覆盖 BepInEx、UniverseLib、EnhanceGameplay、Unity、游戏或其它外部依赖。本目录不重新分发历史完整环境。界面从本机已安装字体读取微软雅黑，未附字体文件。
