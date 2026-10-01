# 大侠立志传多功能修改器 v1.1.0

[English](README.md) | **简体中文**

基于HaxxToyBox的《大侠立志传》修订研究归档。结果仅限记录中的环境，不保证其它环境的适配或效果，不提供支持或更新承诺，详见[使用边界](../../TERMS_ZH.md)。

记录日期：**2026-09-30** · 游戏 **V1.2.0818 75 / Steam Build 24794582** · Windows 11 x64 · 工具界面仍为中文。

[成品归档](https://github.com/Haaaaa96/single-player-trainers/releases/tag/wulin-toybox-v1.1.0) · [操作说明](GUIDE_ZH.md) · [开发记录](DEVLOG_ZH.md) · [源码](../../sources/wulin-toybox) · [构建说明](../../sources/wulin-toybox/BUILD_ZH.md) · [校验值](SHA256SUMS.txt)

## 本版变更与范围

v1.1.0修复姓名／头像／属性读取、跨分类物品搜索、天赋搜索与增删、武学列表滚动和按钮布局；调整中文字体与提示，修复快捷键短按录入及Esc取消的问题。

插件包含当前队伍人物编辑、物品、天赋、金钱、时间暂停、战后恢复、不遇敌、移动／游戏速度、送礼辅助、能力经验倍率和成就选项。武学上限扩展仍依赖原EnhanceGameplay模块。人物页展示31项信息，历史检查覆盖11项普通武学显示和正常升级。

## 归档包边界

WulinToyBox-v1.1.0-plugin.zip用于更新已有兼容前置环境，不包含BepInEx、.NET、UniverseLib、EnhanceGameplay或Unity库。备份存档和原HaxxToyBox.dll，从原来源取得前置，按[操作说明](GUIDE_ZH.md)安装。Tab打开后，左下角应显示HaxxToyBox v1.1.0。

启动慢尚未彻底解决。历史回归重点是主角属性、搜索、天赋、武学界面及部分辅助开关；队友、送礼和能力经验倍率的此前使用情况与本版测试分开记录。没有执行永久成就解锁。

公开源码是脱敏快照，需要本地游戏／前置程序集。本轮未构建或运行，不承诺与历史成品精确一致。

## 许可

- **HaxxToyBox：**原作者Haxx，源码[neeetman/WuLinToyBoxMod](https://github.com/neeetman/WuLinToyBoxMod)，Apache-2.0；见[LICENSE](LICENSE.txt)和[NOTICE](NOTICE.txt)。
- **EnhanceGameplay：**原作页作者字段为630444540，投稿账号gmhaxx；见[原作页](https://mod.3dmgame.com/mod/195081)。
- **参考整合包：**由masterZP.于2024-02-25发布，整合发布者与组件原作者分开署名；见[原整合帖及前置来源](https://bbs.3dmgame.com/thread-6489560-1-1.html)。

保留各组件原有署名和许可，本归档不重新分发未经核实的第三方依赖。
