# WorldApartTrainer 源码与构建说明

[English](BUILD.md) | 简体中文

这是2026-10-02整理的脱敏研究源码快照，来源于v1.3 `read-performance-1`工作区，
包含修改器实现、技术接口规格、构建脚本与离线回归源码。程序界面仍为中文。
**本次公开整理没有构建程序，也没有运行游戏或做实机功能测试。**

## 缺失输入与复现边界

| 未公开输入 | 原因 | 影响 |
| --- | --- | --- |
| `alchemy_specs.json` | 同时包含技术元数据及复制的游戏天赋配置、中英文描述。 | 炼丹适配器、上下文及相关测试无法导入，程序功能初始化也可能失败。 |
| `photostone_catalog.json` | 包含提取的角色、奖励和互动配置。 | 留影适配器及相关测试导入失败。 |
| `engine_game_types.json` | 历史提取类型清单不在本次选择的源码集合中。 | `game_runtime/probe.py`的旧`classes`命令缺少输入。 |

未添加空文件、伪造数据、生成器或降级替身。PyInstaller规格仍要求真实的炼丹、留影输入，
缺文件时会失败；完整测试发现也会导入依赖这些输入的模块。因此本目录是可审阅源码，
**不是可以一键复现现有EXE的完整构建包**。完整构建需要另行合法取得、使用匹配输入，
并重新验证。不包含游戏二进制、元数据转储、资源包、存档、运行缓存或私有原始日志。

其余JSON为接口／类型名、偏移、方法签名、短指令前缀及自行编写的校验规则等技术证据。
保留它们不代表授予游戏资产权利，也不声称游戏派生标识属于本项目。安全校验及技术
证据中的哈希保持原样，没有替换成占位值。

## 历史成品身份

归档v1.3 `read-performance-1` EXE的SHA256为
`bed5bd18a201998c3c84811e7efa7eb412868b636ef04b8cc38d65b569d41f05`。
源码基线为`db1d4009b38e55647dda6abc7894bf837a30e3a2`，**叠加当时未提交的工作区修改**；
不能把该提交单独当作最终构建源码。导出前，85个产品模块与20项入包资源均匹配本地
交付记录中的逐文件哈希，归档EXE哈希也匹配。

本公开副本移除了旧作者标签及本机名称，相关隐私测试采用通用示例，将构建解释器默认值
改为PATH中的`python`，并以研究归档说明替换旧发布文案。源码标记注明公开快照身份。
这些变动意味着本副本与归档EXE并非逐字节对应；本次没有提供由该副本重新构建的程序。

## 环境与构建入口

- Windows x64；历史构建使用带Tkinter/Tcl/Tk的Python 3.14.7。
- `requirements-build.txt`固定了Python构建依赖，包括Frida 17.7.3、PyInstaller 6.22.3；
  `requirements-acquisition.txt`记录源码运行环境所需的同版Frida。
- 脚本使用PowerShell 7。`build_standalone.ps1 -Python <路径>`可指定解释器；默认从PATH解析`python`。
- JavaScript契约测试使用Node.js内置模块，没有npm依赖集，本快照没有固定Node精确版本。
- `build_tcl_resources.py`处理已安装Python的Tcl/Tk zip资源与PyInstaller虚拟zipfs路径的兼容。

原构建入口`build_standalone.ps1`创建`.build-venv`、安装固定依赖、运行
`WorldApartTrainer.spec`，然后用`verify_bundle.py`校验包内容。缺少上述资源时不能完成。
`verify_standalone.ps1`会启动指定EXE做隔离离线自检；`verify_release_archive.py`
只检查指定ZIP，不运行其中EXE。

不依赖缺失资源的现有离线测试入口示例：

```powershell
python -m unittest test_write_guard test_runtime_paths test_build_tcl_resources test_verify_release_archive
```

这些测试使用合成夹具或临时文件，不能证明游戏中的效果。本次公开整理没有重跑功能测试。
其余测试源码一并保留供审阅，其中部分导入依赖未公开资源；不能将完整测试发现标为通过。

## 运行与许可边界

读取层使用Windows进程API；原生操作使用共用Frida后台。普通读取及可用性检查不得隐式注入。
运行状态写入用户本机应用数据目录，开发缓存和日志按需在本地生成，这些文件不得入公开库。

第三方完整许可及[组件说明](THIRD_PARTY_NOTICES.md)保留，其中依法需要的版权署名不属于
个人项目致谢。旧`Launcher.cs`与开发启动器EXE不属于独立版PyInstaller构建，本次未导出。

本归档记录个人研究，不承诺适配、持续维护、排错或兼容其它游戏版本、存档与MOD组合。
