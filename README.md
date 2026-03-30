# 海兹解压 (HaiZiJieYa)

一款优雅的 Windows 密码压缩包解压工具，基于 Python + Tkinter + 7-Zip。

## ✨ 特性

- 🔐 **密码自动尝试** - 支持密码本（一行一个密码，# 开头为注释）
- 📦 **多格式支持** - 7z / rar / zip / tar.gz 等常见压缩格式
- 🖥️ **右键菜单集成** - 文件/文件夹右键直接调用
- ⚡ **内嵌 7-Zip 引擎** - 无需安装，任意电脑即插即用
- 🎨 **精美界面** - 现代化 UI，流畅动画
- 🌙 **暗色模式** - 护眼设计

## 📥 下载使用

前往 [Releases](https://github.com/YOUR_USERNAME/haizijieya/releases) 下载最新版本：

```
dist/海兹解压.exe  ← 下载这个，双击直接运行
```

无需安装，下载后双击即可使用。

## 🛠️ 从源码运行

### 环境要求
- Python 3.8+
- Windows 10/11

### 安装依赖
```bash
pip install pyinstaller
```

### 运行程序
```bash
python auto_unzip.py
```

### 打包发布
```bash
pyinstaller --onefile --windowed \
    --name "海兹解压" \
    --icon "app_icon.ico" \
    --add-data "7z.exe;." \
    --add-data "7z.dll;." \
    --add-data "app_icon.ico;." \
    --clean auto_unzip.py
```

## 📁 项目结构

```
haizijieya/
├── auto_unzip.py      # 主程序源码
├── app_icon.ico       # 程序图标
├── app_icon.png       # 图标源文件
├── make_icon.py       # 图标生成脚本
├── README.md          # 本文件
└── LICENSE            # MIT 许可证
```

## 🔧 配置说明

### 密码本格式
创建 `passwords.txt` 文件，一行一个密码：

```
123456
password
admin123
# 这行是注释，会被忽略
```

### 注册右键菜单
运行程序后，右键点击任意压缩文件或文件夹，选择「🔐 海兹解压」即可自动解压。

### 配置文件
程序会在同目录生成 `auto_unzip_config.json` 保存设置。

## 🎯 使用流程

1. 准备密码本 `passwords.txt`（与 exe 同目录）
2. 右键点击压缩包 → 选择「🔐 海兹解压」
3. 程序自动尝试密码本中的所有密码
4. 找到正确密码后自动解压，删除原压缩包
5. 查看解压日志，确认成功

## 📝 开源协议

本项目采用 [MIT License](LICENSE) 开源，欢迎 fork 和 star！

## 🙏 致谢

- [7-Zip](https://www.7-zip.org/) - 开源压缩工具引擎
- [PyInstaller](https://www.pyinstaller.org/) - Python 打包工具
