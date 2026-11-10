[English](BUILD.md) · [简体中文](BUILD_ZH.md)

# 构建 NX2naviTrainer v0.1.1

## 运行与构建要求

- [Windows 版 NX2navi v0.6.1](https://github.com/tangerineturtle1/NX2navi/releases/tag/v0.6.1)。上游要求 Windows 10/11 x64、支持 SSE4.2 的 CPU、16 GB 内存，以及支持 `VK_EXT_external_memory_host` 和 `VK_EXT_mesh_shader` 的 Vulkan 1.3 驱动。上游估算游戏约占 30 GB、启动器约占 1.5 GB，另外需为构建缓存和输出留出空间。
- 自己转储的 **Nintendo Switch 2 版《塞尔达传说：时之笛》1.1.1**。Title ID 为 `0400486024DEC000`，主 NSO 的 Build ID 前缀为 `E0F3CCFAF50065AE`。脚本会核对主 NSO 的 SHA-256 和游戏模块布局。
- 已用该启动器成功构建过游戏，保留匹配的 `app/0.6.1` 构建工具、UCRT64 工具链和 `game/build-cache`，包括重编译和生成的源码、目标文件以及 `link.rsp`。还需保留启动器已提取的原始 ExeFS 和 RomFS。
- 带 `compression.zstd` 的 Python 3.14。本机编译使用 Python 3.14.7 与 NX2navi 自带的 UCRT64 Clang 23.1.5，目标为 `x86_64-w64-windows-gnu`。运行不需要 Cheat Engine、REA 或额外的模拟器。

## 构建和安装

在本源码目录打开 PowerShell。下载指定提交的 MIT 许可目录参考文件，然后将成品构建到新建或空的目录。

```powershell
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Traiver/OOT-SW2SE/de26f03d0a299e39e5536bf68eeef9b251fadba1/editor.html' -OutFile .\oot-sw2se-reference.html
py -3.14 .\build_candidate.py --catalog-reference .\oot-sw2se-reference.html --out .\trainer-build
```

默认安装目录是 `%LOCALAPPDATA%\Programs\NX2navi`，默认游戏目录是其下的 `game`。自定义路径可通过 `--install-root` 和 `--game-dir` 指定。脚本把 `ocarina.exe` 和中间文件输出到 `trainer-build`，不改动原安装目录。

1. 正常退出游戏。先将原 `ocarina.exe` 和 `game/profile` 备份到单独的位置。
2. 将本机生成的 `ocarina.exe` 复制到原 NX2navi 游戏目录。它使用该目录里的运行时 DLL 和游戏数据。
3. 正常启动并读档，打开 **Esc → 金手指**。选好功能和参数后，点击对应按钮执行。物品搜索按回车只筛选列表。
4. 需要恢复原版时，退出游戏后把备份的 `ocarina.exe` 放回去。启动器重新构建游戏也可能覆盖修改器版 EXE。

参见[上游与第三方声明](THIRD_PARTY_NOTICES.md)。发布包提供构建脚本与修改器源码，游戏和上游输入由使用者在本机准备，并遵循各自适用的条款。
