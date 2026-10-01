# WorldApartTrainer 新V1.3 第三方组件说明

本软件使用第三方运行时。第三方代码由各自权利人持有，始终适用各自的许可；本项目原创部分的免费分享约定不限制第三方许可赋予的权利。

## 普通玩家

玩家仍可只下载并运行单 EXE 修改器。本页、源代码附件及替换工具供希望了解、修改或调试第三方组件的人使用，不是游戏运行依赖。

完整材料与对应版本一起提供：[新V1.3 发行页](https://github.com/Haaaaa96/single-player-trainers/releases/tag/worldapart-v1.3-new)。

## 直接运行组件

| 组件 | 版本／来源 | 许可原文 |
|---|---|---|
| Python | 3.14.7 Windows x64 | [Python-LICENSE.txt](licenses/Python-LICENSE.txt)，包括其附带运行时的说明 |
| Frida Python bindings 与原生核心 | 17.7.3；使用未修改的官方 Windows x64 wheel | [Frida-COPYING.txt](licenses/Frida-COPYING.txt) 与 [Frida-COPYING.LIB.txt](licenses/Frida-COPYING.LIB.txt) |
| PyInstaller bootloader 与运行时 hooks | 6.22.3 | [PyInstaller-COPYING.txt](licenses/PyInstaller-COPYING.txt) 与 [运行时版权](licenses/PyInstaller-Runtime-Notices.txt) |

Frida 官方 wheel 的 `_frida.pyd` 与本软件所用文件逐字节一致；发行文件及其 SHA256 见 [来源记录](upstream-binary-provenance.json)。Frida 顶层采用 wxWindows Library Licence 3.1 及其例外，不能据此改变其所包含其他项目的许可。

## Frida 上游构建依赖

为便于审阅和修改，另提供 Frida 17.7.3 的源码、锁定依赖及原始版权/许可资料。其上游 Windows x64 构建清单包含 GLib、GObject/GIO、libgee、JSON-GLib、libsoup、glib-networking、libnice、libusb、TinyCC、QuickJS、Capstone、V8、OpenSSL、压缩库及相关依赖。这些项目分别使用 LGPL、MIT、BSD、Apache 等许可，并非统一采用 Frida 顶层许可。

资料取自本版本上游锁定的源码树；采用 Windows 构建依赖的保守合集，包含一些构建工具和可选后端，不将此合集冒充每个符号的二进制链接清单。原始版权声明和完整许可保留在 [依赖版权与许可目录](notices/)，并同时放入源码附件；源码文件内的版权头也保持原样。

- [固定源码和哈希清单](sources-lock.json)
- [嵌套依赖和编译器依赖清单](nested-lock.json)
- [Frida 原始构建依赖配置](frida-deps.toml)
- [修改和替换第三方库的方法](REBUILD.md)
- [重新获取并核对归档的脚本](fetch_sources.py)

源代码附件名为 `WorldApartTrainer-Frida-17.7.3-sources.zip`，与程序在同一个发行页提供。附件包含上游固定版本源归档、原许可和构建信息，不包含游戏程序、存档、私人开发记录或本项目原创源码。

本项目允许为修改第三方组件、重新链接及调试这些修改而进行必要的替换和反向工程。修改后的软件应清楚标识为自行修改版，不应冒用原版校验值；第三方组件原有权利与义务以其各自许可为准。

源码版本与获取方式已经核对，替换工具已完成离线测试；没有宣称从头重建整个 Frida 工具链后可得到逐字节相同的官方 wheel，也没有将此说明作为法律意见或第三方合规认证。
