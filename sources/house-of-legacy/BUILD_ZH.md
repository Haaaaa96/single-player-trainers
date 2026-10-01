# 构建 HouseOfLegacyTrainer 0.3.0

[English](BUILD.md) | 简体中文

本目录用于个人研究归档。本次导出没有构建、运行测试、启动游戏或进行实机验证，也没有重新构建既有发行文件。

## 前置条件

- Windows x64、PowerShell 7。
- 含 Roslyn 编译器的 .NET SDK；既有构建记录使用 8.0.425。
- 本机安装的《吾今有世家》。既有参考环境为 V0.9.03、Steam build 22970665、Unity 2020.1.14f1c1、Mono x64。
- 官方 BepInEx 5.4.23.5 x64 Mono 解压目录，根目录下须有 `BepInEx/core/BepInEx.dll`、`0Harmony.dll`、`Mono.Cecil.dll`。

不提供游戏程序集、加载器或第三方二进制。编译引用本机游戏的 `House of Legacy_Data/Managed`；前置文件从各自来源取得。SDK 仅用于编译。

## 构建

在本目录中使用 PowerShell 7：

```powershell
./tools/Build.ps1 -GameDir 'X:/Games/HouseOfLegacy' -FrameworkDir 'X:/Tools/BepInEx-5.4.23.5' -Dotnet 'C:/Program Files/dotnet/dotnet.exe'
```

示例路径须替换为本机实际路径。也可设置环境变量 `HOUSE_OF_LEGACY_GAME_DIR` 和 `BEPINEX5_DIR`；未传 `-Dotnet` 时从 `PATH` 查找。所选 SDK 须在 `dotnet.exe` 安装目录下提供 `sdk/<版本>/Roslyn/bincore/csc.dll`。

输出为 `bin/HouseOfLegacyTrainer.dll`，脚本打印 SHA-256，不安装或启动插件。本次仅将构建路径默认值通用化；产品源码与提交 `52932847bb241009d3b78d602c29b8078ee2bdcd` 一致，不宣称可复建出相同哈希。

## 可用离线检查

每条命令分别使用新的 PowerShell 7 进程：

```powershell
pwsh -NoProfile -File ./tests/Test-Guards.ps1
pwsh -NoProfile -File ./tests/Test-Inventory.ps1
```

检查使用真实数据操作源码及有界替身，不加载游戏程序集，不能代替 Unity 界面、保存持久化和实机验证。本次导出未运行这些检查。

## 范围

插件源码为自行实现。BepInEx、Harmony、Mono.Cecil、Unity 及游戏保留各自权利与条款；本目录不提供其二进制或授予其使用权。本次导出未给自行实现的源码新增许可证。
