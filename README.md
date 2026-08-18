<!-- markdownlint-disable MD033 MD041 -->

<div align="center">
    <img src="assets/logo.png" alt="StellaSora-Auto-Helper" width="200" />
    <h1>MaaStellaSora</h1>
    <p>星塔助手（MaaStellaSora）提供自动签到、清理日常等功能，由 MaaFramework 强力驱动</p>
</div>

遇到问题请去Issues反馈，或前往QQ交流群进行反馈

QQ交流群：**1063132902**  密码：**星塔旅人**

> 项目当前仍处于预览版，可能会遇到部分问题

## 功能

- [x] 登录游戏并签到
- [x] 清理活动
- [x] 赠礼
- [x] 五次邀约
- [x] 领取&发送好友干劲
- [x] 领取委托并重新派遣
- [x] 领取任务
- [x] 自动爬塔
- [x] 自动进行指定关卡
- [ ] 自动刷记录（根据优先度）
- [ ] 更多内容实现中

## 安装与使用

> 默认资源支持比例为 16:9 的游戏客户端。本个人 Fork 另提供实验性的 5120×2160 资源；超宽窗口请在资源设置中选择对应的“5120x2160”项目，原有 16:9 资源不受影响。

1. 请选择带有Latest标签的版本 也可以选择带有rc、beta后缀的版本 不要选择带有Nightly、Alpha等后缀的版本
2. 前往 [Github Release](https://github.com/SodaCodeSave/StellaSora-Auto-Helper/releases) 下载对应系统的压缩包 如果不知道是什么就选 MaaStellaSora-win-x86_64-vx.x.x.zip
3. 解压压缩包到任意目录，并且运行依赖库安装.bat
4. 如果需要操控Windows版星塔旅人，使用管理员权限运行 `MFAAvalonia.exe`（使用ADB的话直接启动即可）

维护超宽资源时，在修改 Pipeline 坐标后执行 `python tools/generate_ultrawide_resource.py`；`tools/dev-run.ps1` 与打包脚本也会自动重新生成。

## 鸣谢

本项目由 **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 强力驱动！

本项目部分功能使用 **[MaaPipelineEditor](https://github.com/kqcoxn/MaaPipelineEditor)** 进行辅助编辑

感谢以下开发者对本项目作出的贡献:

[![Contributors](https://contrib.rocks/image?repo=SodaCodeSave/StellaSora-Auto-Helper&max=1000)](https://github.com/SodaCodeSave/StellaSora-Auto-Helper/graphs/contributors)

## 相关项目

- **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 基于图像识别的自动化黑盒测试框架
- **[MFAAvalonia](https://github.com/SweetSmellFox/MFAAvalonia)** 基于 Avalonia 的 通用 GUI。由 MaaFramework 强力驱动！
- **[MaaPipelineEditor](https://github.com/kqcoxn/MaaPipelineEditor)** 可视化阅读与构建 Pipeline，功能完备，极致轻量跨平台，提供渐进式本地功能扩展，无缝兼容新旧项目
