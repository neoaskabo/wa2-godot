# 在 iPhone / iPad 上运行 wa2-godot

本目录的改动让你的项目可以通过 **GitHub Actions 云端编译** 出 iOS IPA，
本机不需要安装 Xcode。

---

## 为什么用云端编译

本机是 macOS 13.7.8 + Intel 处理器，能装的 Xcode 最高只到 15.4，且体积大、
对老机器负担重。GitHub 提供的 `macos-15` 运行器预装了完整 Xcode，
编译过程全部在云端完成，本机只需要一个浏览器。

---

## 改动清单

| 文件 | 改动 | 原因 |
|------|------|------|
| `script/Wa2EngineMain.cs` | 新增 `iOS` 分支 | 原代码只认 Android 的 `/storage/emulated/N/Wa2Res/`，iOS 会落到 `res://assets/`（App 包内、只读），必然报「资源文件夹不存在」 |
| `export_presets.cfg` | 新增 `preset.2`（iOS） | 原项目只有两个 Android 预设 |
| `project.godot` | 移除 `editor_plugins` 段；新增 `window/handheld/orientation=0` | `gde_gozen` 目录被 `.gitignore` 排除、仓库里并不存在，且代码中零引用，留着会让无头导入失败；横屏匹配 1280x720 |
| `.github/workflows/build-ios.yml` | 新增 | 云端编译流水线 |

### iOS 读取资源的路径

```csharp
Wa2Resource.ResPath = OS.GetSystemDir(OS.SystemDir.Documents) + "/Wa2Res/";
```

App 的 Documents 目录已通过两个导出选项对外暴露：

- `user_data/accessible_from_itunes_sharing` → `UIFileSharingEnabled`
- `user_data/accessible_from_files_app` → `LSSupportsOpeningDocumentsInPlace`

---

## 使用方法

### 1. 推到 GitHub

```bash
git add .
git commit -m "Add iOS export support"
git push
```

### 2. 触发编译

仓库页面 → **Actions** → **Build iOS IPA (unsigned)** → **Run workflow**

首次约 30–60 分钟（要装 .NET iOS workload + Godot 导出模板 + 编译）。

### 3. 下载产物

编译结束后在 run 页面底部下载 `wa2-ios-unsigned`。

---

## 签名与安装（免费 Apple ID）

> 未签名的 IPA **装不进** 非越狱的 iPhone/iPad，这是苹果的限制。
> 免费 Apple ID 无法在 CI 里自动签名（强制 2FA、session 频繁失效），
> 所以改成「云端出未签名包 + 本地工具签名」。

推荐工具（任选一个）：

| 工具 | 平台 | 说明 |
|------|------|------|
| **SideStore** | 设备端 | 装好后在手机上自签自刷，7 天到期可本机续期，最省心 |
| **AltStore** | Windows / macOS | 电脑上跑 AltServer，每 7 天连同一 WiFi 自动续签 |
| **Sideloadly** | Windows / macOS | 拖入 IPA → 填 Apple ID → 安装，操作最简单 |

**免费账号的限制**：
- 签名 7 天过期，到期需重新签名安装
- 最多同时 3 个侧载 App
- 游戏存档在 App 的 Documents 里，只要不卸载就不会丢，重新覆盖安装不影响

---

## 拷贝游戏数据

iOS 没有「手机根目录」，数据要放进 App 沙盒：

1. 用数据线连接手机，打开 **Finder**
2. 侧边栏选中你的 iPhone → 点 **文件** 标签页
3. 在列表里找到 **WhiteAlbum2**，把 PC 版游戏文件夹重命名为 `Wa2Res` 后拖进去

> ⚠️ 不要多套一层目录。正确结构是 `Wa2Res/` 下面直接是 `BGM.PAK`、`script.pak` 等文件。

也可以用 **文件 App** → 我的 iPhone → WhiteAlbum2 导入。

---

## 已知限制

1. **Godot 的 C# iOS 导出是实验性功能**（官方原话）。第一次跑有可能失败，
   需要看 Actions 日志调整。
2. **语言固定为中文**。Android 靠 `command_line/extra_args="cn"` 传参，
   iOS 导出预设没有这个选项，代码里默认 `Language.CN`。要日文版需另想办法。
3. **视频播放不可用**。`Wa2Resource.GetMovie` 已被原作者注释掉，开场影片不会播。
4. **最低 iOS 14.0**，同时支持 iPhone 和 iPad（`targeted_device_family=2`）。
5. iPad 是 4:3 而画面是 16:9，上下会有黑边（正常）。

---

## 后续若要改成签名版本

1. 加入 Apple Developer Program（$99/年）
2. 在 `export_presets.cfg` 的 `preset.2.options` 里填：
   - `application/app_store_team_id` → 你的 Team ID
   - `application/code_sign_identity_release` → `Apple Distribution`
   - `application/provisioning_profile_uuid_release` → 描述文件 UUID
   - `application/export_project_only=false`
3. 把证书和描述文件存成 GitHub Secrets，在 workflow 里导入钥匙串
4. 此时 Godot 会自己跑 `xcodebuild archive` + `-exportArchive` 直接产出已签名 IPA
