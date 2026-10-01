# 修改与替换 Frida 17.7.3

本页供希望修改第三方库的开发者使用，普通玩家不需要进行这些步骤。对应材料在 [worldapart-v1.3-new 发行页](https://github.com/Haaaaa96/single-player-trainers/releases/tag/worldapart-v1.3-new)，源码附件名 `WorldApartTrainer-Frida-17.7.3-sources.zip`。

## 源码组成

`sources/` 保存未经修改的固定上游源码归档；`sources-lock.json` 记录 Frida 主组件、Windows SDK 依赖及编译工具的提交和 SHA256，`nested-lock.json` 记录 GLib 嵌套依赖以及 Frida 编译器/裸机后端所用的锁定 npm、Go 包。归档保持每个上游项目的目录和版权声明，不应删除其源文件内的版权头。

Frida 本体、frida-core、frida-gum、frida-python 和 releng 对应 17.7.3。上游 releng 提交为 `7ed66fe6870f2881f9b663942e90db2757ba0682`；它自己的 `deps.toml` 是 SDK 源码版本及构建参数的来源。保留编译脚本、Meson、tomlkit、Vala、pkg-config 和 Ninja 的源码。通用操作系统及编译器环境需由开发者另行准备。

源码合集比 Windows 实际链接集合更宽，包含构建工具和可选后端；没有纳入仅用于其他平台的 libiconv、libunwind、libdwarf、libbpf、SELinux 等依赖。源目录里的上游 `.gitmodules`、Meson wraps、`package-lock.json`、`go.mod` 和 `go.sum` 保留了进一步获取/重建关系。npm 归档按锁文件 integrity 核对；Go 归档另有 SHA256，原 `go.sum` 一并保留，完整编译时仍应运行 Go 本身的校验。

## 构建兼容的原生库

参考 [Frida 官方构建说明](https://frida.re/docs/building/)；固定版本的 `configure.bat`、`make.bat` 和 `releng/meson_configure.py` 是本页命令的依据。Windows 开发环境需要 x64 C/C++ 编译工具链、Python、Git、Node.js；保留编译器后端时还需要上游要求的 Go 版本（本版要求至少 1.24.3）。本页不自动安装这些工具。

一种保留正常 Git 版本检测的方式：

```powershell
git clone --branch 17.7.3 --depth 1 https://github.com/frida/frida.git frida-17.7.3
Set-Location frida-17.7.3
git submodule update --init --recursive --depth 1
```

修改需要修改的依赖源码，并使用上游的 Meson wrap/SDK 构建配置指向修改后的源码。**修改 GLib 等依赖时须禁用预编译 SDK，否则构建可能仍链接未修改的预编译库。** `configure.bat` 的 `--without-prebuilds=sdk` 用于从源码构建 SDK 依赖。下面的配置限定 Python bindings，关闭无关语言绑定：

```powershell
$env:FRIDA_VERSION = '17.7.3'
.\configure.bat --host=windows-x86_64 --without-prebuilds=sdk -- -Dfrida_python=enabled -Dfrida_node=disabled -Dfrida_clr=disabled -Dfrida_swift=disabled -Dfrida_qml=disabled -Dfrida_tools=disabled
.\make.bat
```

也可使用上游 `releng/deps.py build --bundle=sdk --host=windows-x86_64` 重建 SDK。原始配置及 `--help` 中提供工具链、SDK 和路径选项。归档的完整重新编译没有在本次修改器发布验收中执行；以上是依据固定上游脚本整理的构建路线，不声称无需开发环境即可一键编译，也不保证与官方构建字节完全相同。

生成的 `_frida.pyd` 必须是 Windows x64、Python ABI 兼容的 Frida 17.7.3。保持 `frida.__version__` 为 17.7.3，因为修改器按这个已适配接口版本检查连接组件；没有针对原生库内容的哈希锁。修改后的库自身是否仍符合接口/行为约定由其开发者验证。

## 将自己的库放回单文件程序

附带 `replace_frida.py` 直接重写 PyInstaller 外层归档中的 `frida/_frida.pyd`，保留其余压缩条目、Python 字节码、资源和启动器原字节。它使用 Python 标准库，不需要修改器原创源码，不重新编译修改器，也不需要连接游戏。

```powershell
python replace_frida.py --input WorldApartTrainer.exe --frida .\custom\_frida.pyd --output WorldApartTrainer-custom.exe
.\WorldApartTrainer-custom.exe --self-test .\offline-check.json
```

`--output` 必须是尚不存在的新文件，原版不会被覆盖。可加 `--expected-sha256` 核对输入 EXE。替换后 EXE 哈希必然改变，不能继续使用原版校验值。脚本仅处理未签名的本版 PyInstaller 单文件归档；它拒绝 32 位库、重复条目和损坏目录。完成自测后再自行验证所作改动；不要用修改版本去强制接管已存在的健康游戏后台。

历史 v1.0 离线测试向原生库添加无执行效果的标记，替换进 EXE 后，真实冻结程序成功导入新库，并完成版本、16 页、布局检查；其余归档条目逐字节保持。这个测试证明替换封装和加载路径可用，不等于测试任意修改库的游戏行为。

本项目不限制按第三方许可对第三方组件所作的修改、替换、重新链接及为此进行的调试。替换辅助脚本使用 [MIT 许可](TOOL_LICENSE.txt)；这不改变第三方源码或修改器原创代码的许可。

新V1.3 沿用相同版本的第三方运行时及原生 Frida 库；本轮仅核对身份和材料，未重复执行库替换或游戏测试。
