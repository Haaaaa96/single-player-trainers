[English](README.md) | 简体中文

# 单机游戏修改器研究记录

记录个人对单机游戏修改器开展的实验、实现与修复。

本仓库集中保存经过选择的源码快照、开发记录和版本文件，说明尝试过什么、实际观察到什么，以及哪些部分尚未验证。

**仅作研究归档，按现状提供。** 结果仅限记录中的环境，不保证其他电脑、游戏版本或 MOD 组合的适配情况及使用效果，自行取用并承担风险。不提供使用支持、问题受理或功能请求渠道，也不承诺持续维护。

## 项目目录

| 项目 | 归档版本 | 实现方式 | 入口 |
|---|---|---|---|
| 不问凡尘 / World Apart | v1.3，同版本读取优化 | Python 独立修改器与共用原生后台 | [项目说明](games/worldapart/README_ZH.md) · [源码](sources/worldapart) · [开发记录](games/worldapart/DEVLOG_ZH.md) · [版本文件](https://github.com/Haaaaa96/single-player-trainers/releases/tag/worldapart-v1.3-new) |
| 吾今有世家 / House of Legacy | v0.3.0，实验版本 | Unity Mono 游戏中的 C# 插件 | [项目说明](games/house-of-legacy/README_ZH.md) · [源码](sources/house-of-legacy) · [开发记录](games/house-of-legacy/DEVLOG_ZH.md) · [版本文件](https://github.com/Haaaaa96/single-player-trainers/releases/tag/house-of-legacy-v0.3.0) |
| 大侠立志传 / Hero's Adventure | WulinToyBox v1.1.0 | 既有 IL2CPP 插件的定向修订 | [项目说明](games/wulin-toybox/README_ZH.md) · [源码](sources/wulin-toybox) · [开发记录](games/wulin-toybox/DEVLOG_ZH.md) · [版本文件](https://github.com/Haaaaa96/single-player-trainers/releases/tag/wulin-toybox-v1.1.0) |

## 背景

研究从本机的少量游戏数值修改开始，逐步涉及对象发现、运行时校验、原生会话复用和游戏内界面。记录保留失败路线及验证边界，也保留已经奏效的改动；目的是保存研究过程，不是承诺长期维护的软件产品。

## 技术方式

- **不问凡尘：** Python/Tk 界面、IL2CPP 元数据与对象校验、有界内存发现，以及统一后台派发已审阅的游戏调用。实际功能保护与版本提示分开处理。
- **吾今有世家：** BepInEx 5 插件，包含数据修改保护、暂停状态所有权和开窗期间的输入隔离。
- **WulinToyBox：** 定向修订上游插件的数据读取、搜索、列表、输入处理和界面，原依赖及许可证分别保留。

## 源码与开发

构建入口见各项目的 `BUILD_ZH.md`。这里公开的是经过隐私检查的源码快照，不是私人工作目录或其 Git 历史的镜像。部分构建输入属于游戏或第三方，未随源码提供；各项目说明列出实际缺项。

源码导出不包含游戏程序、游戏程序集、存档、运行日志、凭据或个人配置。此次公开源码不代表重新构建并实测过，也不保证能逐字节复现旧程序。修改器本身的界面仍可能是中文。

- [源码范围与构建入口](sources/README_ZH.md)
- [开发方式与经验](docs/DEVELOPMENT_ZH.md)
- [隐私与来源边界](docs/PRIVACY_ZH.md)
- [归档文件校验值](releases.json)

## 仓库结构

```text
README.md / README_ZH.md       英文与中文入口
games/<game>/                 项目介绍、操作说明和开发记录
sources/<game>/               选定实现、测试及构建说明
docs/                         开发方式和隐私边界
third_party/                  必要许可及对应源码／构建材料
releases.json                 归档文件身份
```

Releases 保留历史文件。包内可能保留过去的发布文案，不构成当前支持承诺。自动生成的 Source code 是仓库快照；具体程序和另附依赖源码由有明确名称的附件区分。哈希仅核对文件身份，不是安全或兼容性认证。

## 许可

原创源码公开可读，本次不因此自动为其套用新的开源许可证。WulinToyBox 与第三方组件保留原有许可和必要署名；游戏名称与资源归相应权利人所有。

[归档使用边界](TERMS_ZH.md) · [第三方许可](THIRD_PARTY_NOTICES_ZH.md)
