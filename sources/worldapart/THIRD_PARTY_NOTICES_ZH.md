# 第三方组件与许可文本

[English](THIRD_PARTY_NOTICES.md) | 简体中文

WorldApartTrainer 独立版包含下列第三方运行时组件。本文件提供组件来源和随包许可文本索引；各组件的具体条款以对应原文为准。

| 组件 | 本版使用版本 | 来源 | 随包文本 |
| --- | --- | --- | --- |
| Python | 3.14.7，Windows x64 | [Python](https://www.python.org/) | [Python-LICENSE.txt](licenses/Python-LICENSE.txt) |
| Frida Python bindings | 17.7.3 | [Frida](https://frida.re/)、[frida-python](https://github.com/frida/frida-python) | [Frida-COPYING.txt](licenses/Frida-COPYING.txt)、[Frida-COPYING.LIB.txt](licenses/Frida-COPYING.LIB.txt) |
| PyInstaller bootloader 与运行时 hooks | 6.22.3 | [PyInstaller](https://pyinstaller.org/)、[源码](https://github.com/pyinstaller/pyinstaller) | [PyInstaller-COPYING.txt](licenses/PyInstaller-COPYING.txt)、[运行时 hooks 版权原文](licenses/PyInstaller-Runtime-Notices.txt) |

Python、Frida 和 PyInstaller 的许可文件逐字节复制自本次构建所用的官方发行包。Python 的许可文件还包含此 Windows 运行时所附带的部分依赖条款，包括 bzip2、libffi、Zstandard、Apache License 2.0、Tcl 和 Tk。Tcl/Tk DLL 内的原有 `license.terms` 也保留在独立版中。

Frida 的 `COPYING` 使用 wxWindows Library Licence 3.1，并引用 GNU Library General Public License。补充的 `Frida-COPYING.LIB.txt` 是 [GNU 官方提供的完整 GNU Library General Public License v2.0 文本](https://www.gnu.org/licenses/old-licenses/lgpl-2.0.txt)，版本为 June 1991；原始 `COPYING` 中的例外条款一并保留。

PyInstaller 的 `COPYING.txt` 包含其 bootloader exception 和不同组成部分的许可说明。独立版使用的运行时 hooks 的 Apache-2.0 版权头另附于对应文件。

以上原作者许可文本没有因本项目打包而改写。本次打包没有修改所列 Python、Frida、PyInstaller 发行组件的源码。
