# HookshotTrainer 0.2.25-dev

[English](README.md)

这是为 Windows x64 版 Hookshot v2.3.1 制作的《塞尔达传说：时之笛》内置中文修改器。面板随游戏运行，宿主 EXE 与 Vulkan 渲染 DLL 成对构建。本源码归档包含 0.2.25 的空瓶删除功能，以及上一版对大型计算着色器的兼容修复。

## 游戏内操作

按 **反引号键**（通常在 Esc 下方）开关面板。进入 **道具**，选中 **空瓶**（`Item_Bottle`），点击 **删除空瓶**，每次删除一个。装有内容的瓶子、剧情信瓶，以及童年或成年道具栏已分配的瓶子均受保护。若所有空瓶都已分配，先在游戏内更换装备。面板会等到库存和持有标记都清除才显示成功，超时不会自动重发。

面板还包含生命、卢比、弹药、魔力、道具搜索和增减、装瓶、传送、飞行、主线提示、实时地图及基础游戏迷宫指引。按 **F6** 起降，或在仅连接一个手柄时按住 **ZL＋ZR＋右摇杆按下**（Xbox 为 **LT＋RT＋RS**）半秒。全部松开后才接受下次组合。Master Quest 迷宫指引未接入。

## 自行构建

需要 **Windows x64、PowerShell 7+ 和 v2.3.1 Windows Builder 工具包**。使用包内带有 `compression.zstd` 的 Python 3.14、LLVM-MinGW、CPM 依赖，以及针对本机 CPU、使用性能剖析文件的构建配置。单独检出上游源码不会附带这些依赖。对应上游提交为 [Hookshot 5d3de41](https://git.notrexed.dev/Hookshot/Hookshot/src/commit/5d3de413df5587a1896b2b7df6a3a385ae24195a)。[上游版本页](https://git.notrexed.dev/Hookshot/Hookshot/releases/tag/v2.3.1)

自备游戏转储，游戏目录应有 `romfs/` 和 `.hookshot_exefs/`，包含中英文消息表。原始 `main` 的 SHA-256 为 `2591fb99008d0814f8056c3f36b36790048ed857ff0ae2bb3a4c1e37b960a4de`。物品、任务与地图表均在本地生成。另需固定版本的 HTML 物品对照表，SHA-256 为 `42d7777267e7959b958c8e6f8d1c247794bf0931ba2c3614628bbdc678e0de37`。[Traiver 的 editor.html 原文件](https://raw.githubusercontent.com/Traiver/OOT-SW2SE/de26f03d0a299e39e5536bf68eeef9b251fadba1/editor.html)

在本源码目录打开 PowerShell。示例将输入和各个输出放在同级目录，请按实际位置调整。准备一份单独使用的 Builder 工具包副本。

```powershell
$workspace = (Resolve-Path '..').Path
$builder = Join-Path $workspace 'HookshotBuilder'
$game = Join-Path $workspace 'GameDump'
$reference = Join-Path $workspace 'editor.html'
$stage = Join-Path $workspace 'HookshotBaseBuild'
$out = Join-Path $workspace 'HookshotTrainerBuild'
$tools = Join-Path $builder 'versions/v2.3.1/HookshotBuilder/tools'
$python = Join-Path $tools 'python/python.exe'
```

1. **准备并保留原版构建。** 将完整上游工具包放入 `$tools`。使用尚无 `work-v2.3.1` 的独立 Builder 目录，另选不存在的暂存目录。脚本先备份并修复这份工具包的 Vulkan 源码，再以 `HOOKSHOT_KEEP_BUILD_FILES=1` 完整编译上游，保留游戏和渲染对象、链接清单、生成源码、两套性能剖析文件及原版 EXE/DLL。此步骤关闭着色器预编译。需为游戏、暂存目录和编译产物留足磁盘空间。如果已有符合这些条件、含着色器修复的保留构建，可直接执行第 2 步。

    ```powershell
    .\Prepare-Builder.ps1 -BuilderRoot $builder -Game $game -Stage $stage
    ```

2. **生成修改器。** 指定源码、游戏和 Builder 目录以外且尚不存在的输出目录。启用了 DLSS 的原构建需要匹配的本地 NGX SDK，放在 `$tools/ngx-sdk`，或通过 `HOOKSHOT_NGX_SDK` 指定。若原构建启用了 dav1d，其 CPM 缓存中也须保留对应头文件和静态库。脚本会检查 Vulkan 源码与编译对象是否含着色器修复。

    ```powershell
    & $python -B -X utf8 .\trainer\build_candidate.py --builder-root $builder --game $game --reference $reference --out $out
    ```

3. **本地使用。** 构建会报告两个文件的 SHA-256。关闭游戏，备份现有的 `bin/hookshot.exe`、`bin/hookshot_vk.dll` 和存档，再将新生成的一对文件按同名放入匹配游戏的 `bin` 目录。使用上游原有的其他运行文件；需要回退时同时恢复旧版两件套。上游 Update 可能覆盖这两个文件。本地重建将产生自己的构建标识，程序可能依赖构建机器的 CPU 特性。

## 验证范围与权利

11 月 17 日安装的参考构建是 `6d5c41081406`，修改器 ABI 14、渲染 API 23。公开版源码已用 v2.3.1 保留构建重编。包括修改器核心在内的 12 份生成头文件与参考候选逐字节一致。空瓶增删的状态与保护条件、着色器长度边界通过离线测试。本次打包验证未运行游戏。物品栏刷新、保存重载、重启和其他系统或 MOD 组合仍缺少此次实机验证。

Hookshot 上游源码采用 GPLv3，各第三方组件的权利声明、许可证与商标继续适用。库存字段参考 Traiver 的 OOT-SW2SE（MIT）；玩家对象与背包研究曾参考 Hookshot-AllowGames 的公开实现。本包提供接入代码、测试和构建脚本；游戏资源、HTML 对照表、SDK、编译器、生成表、存档和链接后的二进制由使用者自行准备或在本地生成。此处为个人研究归档，不承诺适配或技术支持；独立原创修改器代码没有另行统一授予新许可。[Hookshot GPLv3](notices/Hookshot-COPYING.txt) · [OOT-SW2SE 许可](notices/OOT-SW2SE-LICENSE.txt) · [Hookshot-AllowGames 参考](https://github.com/AllGamersRD17/Hookshot-AllowGames/blob/95b9c20cffc4a92485bf9a84e0649c3cec027a8c/host/hos_main.c)
