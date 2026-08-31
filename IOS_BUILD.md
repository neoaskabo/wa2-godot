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
| `script/Wa2EngineMain.cs` | `GetVideoPath()` 在 iOS 返回空串 | 让影片走「文件不存在」的既有分支，而不是卡在永远等不到帧的播放器上 |
| `addons/gde_gozen/VideoPlayback.cs` | 新增 API 兼容的占位实现 | **关键修复**：`addons/gde_gozen/` 被上游 `.gitignore` 排除，仓库里根本没有这个目录；但 `Wa2EngineMain.cs` 直接引用了 `VideoPlayback` 类型、`main.tscn` 也把它挂在 `VideoStreamPlayer` 节点上。所以全新 clone 根本编译不过（CS0246），Godot 内部的 `dotnet publish` 必失败 |
| `script/Weather.cs` | 新增占位实现 | `scene/weather.tscn` 引用它但上游从未提交该文件，导出时一直报 `Cannot load C# script file`。该场景没有被任何地方实例化 |
| `export_presets.cfg` | 新增 `preset.2`（iOS） | 原项目只有两个 Android 预设 |
| `project.godot` | 移除 `editor_plugins` 段；新增 `window/handheld/orientation=4` | 前者指向不存在的 `gde_gozen/plugin.cfg`，会让无头导入失败。orientation 用 `4`（sensor landscape），横屏匹配 1280x720 且支持左右两个方向；若用 `0` 则被硬锁在 LandscapeLeft 单向 |
| `.gitignore` | 放行 `addons/gde_gozen/VideoPlayback.cs` | 让上面那个占位实现能被提交 |
| `.github/workflows/build-ios.yml` | 新增 | 云端编译流水线 |

### iOS 读取资源的路径

```csharp
string userDir  = OS.GetUserDataDir();                 // <App>/Documents
string resRoot  = userDir.PathJoin("Wa2Res");
Wa2Resource.ResPath = resRoot + "/";
SavPath             = userDir.PathJoin("sav") + "/";
```

**必须用 `OS.GetUserDataDir()`，不能用 `OS.GetSystemDir(OS.SystemDir.Documents)`。**

Godot 4.5.1 里 iOS 只覆盖了前者：

| API | iOS 上的实际返回值 | 来源 |
|-----|------------------|------|
| `OS.GetUserDataDir()` | `/var/mobile/.../Documents`（绝对路径） | `OS_AppleEmbedded::get_user_data_dir()`，取 `NSDocumentDirectory` |
| `OS.GetSystemDir(SystemDir.Documents)` | `"."` | 基类 `OS::get_system_dir()` 的默认实现，iOS 从未覆盖 |

用后者的后果是 `ResPath` 变成 `"./Wa2Res/"`，相对路径会被解析到**只读的 App 包内**，
于是无论往文件共享目录里放什么都读不到（这是第一版 IPA 的 bug）。

App 的 Documents 目录已通过两个导出选项对外暴露：

- `user_data/accessible_from_itunes_sharing` → `UIFileSharingEnabled`
- `user_data/accessible_from_files_app` → `LSSupportsOpeningDocumentsInPlace`

首次启动会自动创建 `Wa2Res/`、`Wa2Res/IC/`、`Wa2Res/movie/` 和 `sav/`。
存档放在 `sav/`（与 `Wa2Res/` 平级），这样重新覆盖游戏数据不会清掉进度。

排查时可以看这几行日志。除了 Xcode 控制台，App 还会把它们写进
`Documents/wa2-log.txt`，用「文件」App 就能取回，不必连线：

```
[wa2] iOS user dir : /var/mobile/Containers/Data/Application/.../Documents
[wa2] iOS res path : .../Documents/Wa2Res/
[wa2] res dir      : .../Documents/Wa2Res/
[wa2] res dir entries:
[wa2]   .../Documents/Wa2Res/BGM.PAK
```

### 排查：雪花是白方块、点标题后黑屏

**这两个是同一个原因：PCK 里根本没有美术资源。**

上游 `.gitignore` 排除了 `assets/grp/`、`assets/se/`、`assets/fonts/cn/`、
`assets/fonts/jp/`（都是从游戏里提取的素材）。`git clone` 下来这些目录是空的，
于是 Godot 导出的 PCK 缺了 132 个文件。在已构建的 PCK 里核对：

| 关键字 | 在 PCK 中的出现次数 |
|--------|------------------|
| `main.tscn` | 2 |
| `.gdshader` | 25 |
| `font.map` | 1 |
| `weather.png` | **0** |

后果：

- `res://assets/grp/weather.png` 取不到 → `AtlasTexture.Atlas` 为 null →
  `GPUParticles2D` 退化成默认白色方块
- 标题和菜单用的 `T*.png`、`sys_*.png` 全部缺失 → 画面全黑

**资源不入库，而是在编译期还原。** `tools/extract_assets.py` 从上游官方
Android APK 里把资源无损取回来 —— APK 里存的是 Godot 的导入产物：

```
assets/assets/<相对路径>.import           → 记录原始路径
assets/.godot/imported/<名字>-<md5>.ctex → "GST2" 魔数 + 56 字节头 + 图片数据
```

因为是无损存储（91 个 WebP、39 个 PNG），可以原样还原。

两个坑：

1. **APK 的 zip 没有设 UTF-8 标志位**，Python 的 `zipfile` 会按 cp437 解码，
   `assets/grp/煙.png` 会变成乱码。要手动 `name.encode('cp437').decode('utf-8')`
   再解回去，否则中文/日文文件名的资源会整批丢失。
2. `assets/se/*.WAV` 在 APK 里只有 Godot 的 `.sample` 二进制资源，解不划算，
   所以脚本合成短促的按键音代替 —— 缺的是 ext_resource，会让
   `BasePage.tscn` 这类场景加载失败。

`assets/grp/sys_01013.png` 是位图字体（`importer="font_data_image"`），
APK 里只剩烘焙后的 FontFile，源图拿不回来，用透明占位图代替，
存档列表的文字会退回默认字体。

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
3. 在列表里找到 **White Album 2**，把 PC 版游戏文件夹重命名为 `Wa2Res` 后拖进去

> ⚠️ 不要多套一层目录。正确结构是 `Wa2Res/` 下面直接是 `BGM.PAK`、`script.pak` 等文件。

也可以用 **文件 App** → 我的 iPhone → White Album 2 导入。

首次启动会自动创建这些目录，如果没看到可以先启动一次 App：

```
Documents/
├── Wa2Res/          ← 在这里放游戏数据
│   ├── IC/          ← 自动创建
│   └── movie/       ← 自动创建（没有也能进游戏，会自动跳过 MV）
└── sav/             ← 自动创建，存档放这里
```

存档特意放在 `Wa2Res` **外面**，这样以后重新拷游戏数据不会把进度一起删掉。

> ⚠️ iOS 的 APFS 默认**大小写敏感**。如果从 PC 拷过来的文件名是 `voice.pak` 而代码找的是
> `VOICE.PAK`，会加载失败。绝大多数 PC 版原盘文件名本来就是大写的，正常情况下不用管；
> 万一提示文件不存在，先检查大小写。

---

## 已验证的构建结果

`Actions` 运行成功后，产物的实际情况：

| 项目 | 值 |
|------|-----|
| 架构 | `arm64`（iPhone + iPad 通用） |
| 最低系统 | iOS 14.0 |
| Bundle ID | `com.example.wa2ios` |
| 版本 | 0.2.8 |
| 文件共享 | `UIFileSharingEnabled = true`（可通过 Finder / 文件 App 拷数据） |
| 方向 | 横屏（左 + 右） |
| 显示名 | `White Album 2` |
| 体积 | 约 46 MB（IPA 压缩包），解压后约 123 MB |
| 游戏代码 | 在 `Frameworks/wa2.framework/wa2`（约 24 MB，NativeAOT 编译产物） |

> Godot 的 iOS/.NET 导出使用 **NativeAOT**，包里**没有** `.dll`，
> C# 代码被编进了 framework。用 `strings Frameworks/wa2.framework/wa2 | grep Wa2EngineMain`
> 可以确认游戏代码是否真的进去了（类型名是 ASCII，能被 `strings` 直接扫到）。
>
> 注意：**C# 的字符串字面量在 .NET 元数据里是 UTF-16LE 存的**，
> 用 `strings` 默认（UTF-8 / 最短 4 字节）扫不到，会误判成「新代码没编进去」。
> 要验证字符串字面量得按 UTF-16LE 扫，例如用 Python：
>
> ```python
> data = open("Frameworks/wa2.framework/wa2", "rb").read()
> data.count("[wa2] iOS user dir".encode("utf-16-le"))   # >0 即已编入
> ```

### 排查：读不到 Wa2Res

如果还是提示资源文件夹不存在，游戏启动时会往控制台打这三行，用 Xcode →
Devices and Simulators → Open Console（或 `Console.app` 选设备）能看到：

```
[wa2] iOS user dir : /var/mobile/Containers/Data/Application/<UUID>/Documents
[wa2] iOS res path : /var/mobile/Containers/Data/Application/<UUID>/Documents/Wa2Res/
[wa2] iOS sav path : /var/mobile/Containers/Data/Application/<UUID>/Documents/sav/
```

`res path` 必须是 Documents 下的绝对路径。如果它是 `./Wa2Res/`，
说明拿到的是旧包，重新下载一次。紧接着还会列出该目录下实际有哪些文件，
可以直接看出是不是拷错了层级。

---

## 已知限制

1. **Godot 的 C# iOS 导出是实验性功能**（官方原话）。真机上的运行时问题
   （尤其是 NativeAOT 的裁剪/反射相关）需要实机验证。
2. **语言固定为中文**。Android 靠 `command_line/extra_args="cn"` 传参，
   iOS 导出预设没有这个选项，代码里默认 `Language.CN`。要日文版需另想办法。
3. **视频播放不可用**。原作者的 `gde_gozen`（FFmpeg 的 GDExtension）没有 iOS 构建，
   也无法在沙盒里工作，所以用占位实现替代；`GetVideoPath()` 在 iOS 返回空串，
   影片直接跳过并继续推进剧情，**不会卡住**。
4. **最低 iOS 14.0**，同时支持 iPhone 和 iPad（`targeted_device_family=2`）。
5. iPad 是 4:3 而画面是 16:9，上下会有黑边（正常）。

---

## 编译流水线自带的三道保险

之前踩过的坑：Godot 内部的 `dotnet publish` 失败时 **仍然返回 0**，
于是流水线全绿，但产出的 `.app` 里没有任何游戏代码（装上去就是黑屏）。
所以流水线现在有：

1. **`Preflight - compile C# sources`**：先单独跑一次 `dotnet build`。
   Godot 会吞掉 MSBuild 输出，这一步让真正的 C# 报错（如 CS0246）直接出现在日志里。
2. **导出日志扫描**：导出后 grep `Failed to build project` / `error CSxxxx` /
   `Cannot load C# script file`，命中即失败。
3. **Framework 校验**：确认 `Frameworks/` 里的可执行文件中存在
   `Wa2EngineMain`、`Wa2AdvMain`、`Wa2Resource`、`SubtitleMgr`、`YamlDotNet`，
   缺失即失败。

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
