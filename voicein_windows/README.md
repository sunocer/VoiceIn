# VoiceIn Windows Alpha

这是第一版 Windows 单机服务：后台监听全局 F8、采集本机麦克风、调用火山识别，并把最终文字写入录音开始时的前台窗口，或提交至明确绑定的 Codex 任务。配置页为 `http://127.0.0.1:8766/`。当前用户登录 Windows 后自动启动，托盘图标显示状态。

## 启动

```powershell
python -m pip install -r voicein_windows/requirements.txt
python -m voicein_windows.app
```

也可双击项目根目录的 `启动VoiceIn-Windows.cmd`。启动后会打开默认浏览器；关闭启动窗口会停止服务。当前 Alpha 尚未做托盘图标和安装包。

## 使用

1. 在配置页选择“当前聚焦输入框”或“Codex 当前任务”。
2. 填写火山凭据和资源，保存。凭据用 Windows DPAPI 加密到当前用户的 `%LOCALAPPDATA%\VoiceIn\config.json`，页面不会读回明文。
3. 切回需要输入文字的程序，把光标放在输入位置。
4. 按住 F8 说话，松开后等待最终识别结果。

随时按 `Ctrl+Alt+9` 在“当前聚焦输入框”和“Codex 当前任务”之间切换。托盘图标和系统提示会显示切换结果；红色为录音、黄色为等待识别、蓝色为投递。F8 开始、结束和完成时有短提示音。

普通输入模式在 F8 按下时锁定前台窗口。识别完成前如果切换窗口，应用会保留文字并拒绝写入，防止误投；不会自动按 Enter。Codex 模式使用绑定任务 ID 直接提交消息并触发任务。

## 当前边界

- 语音快捷键支持 Copilot、F8 和自定义组合键。
- 当前窗口识别以窗口句柄和进程校验，一期未细分同一窗口中的多个编辑控件。
- Unicode 键盘注入不适用于密码框、安全桌面、管理员权限高于 VoiceIn 的窗口，部分自绘编辑器可能不兼容。
- 单次仍使用 3 分钟测试上限。
- 配置页会只读扫描本机 Codex 状态数据库，按标题、项目路径和更新时间选择任务并自动填写任务 ID；发送仍使用当前安装版本的内部 IPC，Codex 升级后需重新验证。
- 配置页面不是采音入口，Codex 内置浏览器是否允许网页麦克风不影响本服务采音。

## 测试

```powershell
python -m unittest voicein_windows.test_windows -v
python -m unittest discover -s volc_web -p "test_*.py" -v
```
