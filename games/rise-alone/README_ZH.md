[English](README.md) | 简体中文

# 《重生2我独自逆袭》内置多功能修改器 V1.8.2

适配参考为 Steam Windows 64 位正式版，游戏构建号 26669300。本版修复开启「做选择不限时」后，剧情自动转场偶尔黑屏、无声的问题。

[Windows 完整包](https://github.com/Haaaaa96/single-player-trainers/releases/download/rise-alone-v1.8.2/RiseAloneTrainer-v1.8.2-win64.7z) · [版本归档](https://github.com/Haaaaa96/single-player-trainers/releases/tag/rise-alone-v1.8.2) · [开发记录](DEVLOG_ZH.md) · [源码与构建](../../sources/rise-alone/README_ZH.md)

## 功能

- 主角有 10 项可修改数值，包括金钱、行动力、开场和本场战技点。14 位人物可手动调好感。另有 11 项 NPC 属性，涵盖妹妹性格与能力、盆栽养成和赵总认可度。
- 七项开关分别为行动力不减少、保持零压力、交互人物自动满好感、小游戏自动完成、任务防误选、做选择不限时，以及显示当前可进入的未解锁地点。
- 剧情、手机和邮件选项会显示已确认的收益和任务中断风险。「最佳」优先考虑原剧情中人物好感的净增，行动力不参与排名。做选择前开启「任务防误选」，可用「重选上一步」退回最近一次已记录的选择，撤回之后的进度。

## 安装与使用

1. 退出游戏。在 Steam 库右键游戏，选「管理 → 浏览本地文件」。将完整包一次解压到该目录，确认 `winhttp.dll` 与游戏 EXE 同级。包内含 BepInEx 6.0.0-be.793、运行时和 Unity 基础库。
2. 从 Steam 照常启动，首次运行会生成游戏接口。读档后按 Esc 下方、数字 1 左侧的反引号键，打开或关闭面板。
3. 在「辅助功能」点「保存设置」，七项开关会在换档和重启后沿用。属性、好感和剧情进度用游戏自身的存档功能保存。
4. 其他 MOD 已在使用兼容的 BepInEx IL2CPP x64 环境时，可单独更新 `BepInEx/plugins/RiseAlonePlugin.dll` 以保留自定义加载器配置。需要停用时，退出游戏并移出该文件。

[配图一 · 主角属性](https://github.com/Haaaaa96/single-player-trainers/releases/download/rise-alone-v1.8.2/RiseAloneTrainer-v1.8.2-01-stats.png) · [配图二 · 辅助功能与任务重选](https://github.com/Haaaaa96/single-player-trainers/releases/download/rise-alone-v1.8.2/RiseAloneTrainer-v1.8.2-02-assists.png)。两张图均由本版菜单使用示例数值离线生成。
