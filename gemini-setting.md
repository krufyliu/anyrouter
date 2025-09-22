# 在 macOS 上为 Zed 等 GUI 应用配置 Gemini CLI 环境变量

## 1. 问题根源

在 macOS 中，通过图形界面（GUI）启动的应用（如 Zed）与通过终端启动的进程（Shell Session）拥有独立的环境变量作用域。GUI 应用不会读取 `.zshrc` 或 `.bashrc` 等 shell 配置文件，这导致了环境隔离问题。因此，在一个终端中可以正常运行的 `gemini` 命令，在 Zed 的任务（Task）中会因为无法访问 `GOOGLE_API_KEY` 等关键变量而执行失败。

本文档旨在提供一个一劳永逸的解决方案，让所有 GUI 应用都能正确读取到这些关键的环境变量。

## 2. 前提条件

在开始之前，请确保你已经准备好：

- **API 密钥**: 你的 Gemini API 密钥。
- **自定义请求地址 (可选)**: 如果你使用代理或自定义端点，请准备好完整的 URL。
- **Gemini CLI 已安装**: 确保 `gemini` 命令可以在你的标准终端中正常工作。
- **Zed 编辑器已安装**。

## 3. 推荐方案：使用 `launchd` 设置全局环境变量

这是在 macOS 上为 GUI 应用设置环境变量的最佳实践，配置一次，永久生效。

### 步骤 1: 创建 `LaunchAgents` 目录 (如果不存在)

打开终端 (Terminal.app 或 iTerm)，运行以下命令：

```bash
mkdir -p ~/Library/LaunchAgents
```

# 步骤 2: 创建并编辑 plist 配置文件

## 创建一个名为 environment.plist 的文件，用于定义我们需要的环境变量。

```bash
touch ~/Library/LaunchAgents/environment.plist
```

## 使用 Zed 或任何文本编辑器打开这个新创建的文件，然后将以下 XML 内容完整地复制进去。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "[http://www.apple.com/DTDs/PropertyList-1.0.dtd](http://www.apple.com/DTDs/PropertyList-1.0.dtd)">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>my.startup.env</string>
    <key>ProgramArguments</key>
    <array>
        <string>sh</string>
        <string>-c</string>
        <string>
        launchctl setenv GOOGLE_API_KEY '在此处粘贴你的API密钥';
        launchctl setenv API_BASE_URL '在此处粘贴你的自定义请求地址';
        </string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

步骤 3: 加载配置并重启
为了让系统加载并应用这个配置，你有两种选择：

# 手动加载 (立即生效):

## 在终端中运行以下命令来加载此配置。

```bash
launchctl unload ~/Library/LaunchAgents/environment.plist
launchctl load ~/Library/LaunchAgents/environment.plist
```
