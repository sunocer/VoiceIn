# VoiceIn Windows

VoiceIn 是一个 Windows 单机语音输入助手：按住 F8 说话，松开后调用火山引擎实时语音识别，并把最终文字写入当前窗口，或提交到明确绑定的 Codex 桌面任务。

当前版本：`0.1.0-alpha`

## 功能

- 全局 F8 按住说话、松开识别；
- `Ctrl+Alt+9` 在“当前聚焦输入框”和“Codex 当前任务”之间切换；
- Windows 系统托盘状态、提示音和通知；
- 当前用户登录后自动启动；
- 火山 AppID / Access Token 或 API Key；
- 凭据使用 Windows DPAPI 加密，不写入仓库；
- 普通输入模式只填字，不自动按 Enter；
- 目标窗口变化时拒绝误投并保留最近文字。

## 快速使用

普通用户请下载 GitHub Release 中的 `VoiceIn-0.1.0-alpha-win-x64.exe`，双击运行，在打开的本地配置页填写火山凭据。配置页地址为：

`http://127.0.0.1:8766/`

完整安装、开发构建、卸载与 GitHub 发布方法见 [部署教程](docs/部署教程.md)。产品行为及验收范围见 [Windows MVP 规格](VoiceIn-Windows-MVP规格.md)。

## 重要边界

- 当前是 Alpha 测试版，没有代码签名和自动更新。
- “当前聚焦输入框”目前锁定前台窗口，还没有精确锁定同一窗口内的具体编辑控件。
- Codex 对接使用当前桌面版本的内部 IPC，并依赖本机安装 Node.js；Codex 更新后可能需要适配。
- 音频发送到火山引擎云端识别，自托管应用不代表离线识别。
- 当前单次录音仍有 3 分钟测试上限。

## 源码运行

```powershell
python -m pip install -r voicein_windows/requirements.txt
python -m voicein_windows.app
```

## 测试

```powershell
python -m unittest voicein_windows.test_windows -v
```

## 许可证

本项目尚未选择开源许可证。公开仓库前应先确定许可证；在未附加许可证时，默认版权规则适用，其他人没有自动获得复制、修改或分发许可。
