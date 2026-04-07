# DrinkCat · 喝水喵

[![License: PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm%20Noncommercial-orange.svg)](LICENSE)

一款基于 **Python + PyQt6** 的 Windows 桌面小工具：半透明置顶浮窗记录饮水、联网获取饮水建议与天气文案、系统托盘与超时提醒，并在达成当日目标时给予正向反馈。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| **置顶浮窗** | 半透明、可拖拽，快速点击 `+100/200/250/500 ml` 记一笔 |
| **联网建议** | 结合 IP 归属（含中文地区）与 [wttr.in](https://wttr.in/) 等源获取气温，微调每日目标与提醒间隔 |
| **托盘** | 显示/隐藏浮窗、刷新建议、设置、退出；托盘图标随完成度变化 |
| **喝水提醒** | 超过建议间隔未记录时通过托盘气泡提醒（达标后不再打扰） |
| **目标达成** | 当日首次达标时托盘祝贺 + 置顶对话框文案（同日仅一次） |
| **数据持久化** | 本地 JSON 保存记录与设置 |

---

## 环境要求

- **Windows 10 / 11**（64 位）
- **Python 3.10+**（开发运行推荐 3.11+）

---

## 从源码运行

```bash
git clone https://github.com/<你的用户名>/drinkCat.git
cd drinkCat

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

---

## 打包为 exe

1. 将 **`logo.ico`** 放在项目根目录（与 `drinkCat.spec` 同级），否则打包会报错。  
2. 安装打包依赖并执行脚本（默认带 `--clean`，更换图标后建议保留）：

```bash
pip install -r requirements.txt -r requirements-build.txt
python build.py
```

3. 生成文件：**`dist/drinkCat.exe`**（无控制台窗口）。

若 **exe 已更新但资源管理器仍显示旧图标**，多为 Windows 图标缓存，可尝试注销/重启，或清理 `IconCache` 相关文件后再开资源管理器。

---

## 配置与数据位置

- **设置**：性别、手动每日目标/提醒间隔、浮窗不透明度等（设置里「0」表示沿用联网自动建议）。
- **数据文件**（记录、缓存的天气文案等）：
  - Windows：`%APPDATA%\DrinkCat\data.json`

---

## 项目结构（简要）

```
drinkCat/
├── main.py              # 入口
├── build.py             # 一键打包
├── drinkCat.spec        # PyInstaller 配置
├── logo.ico             # 打包用程序图标（需自备）
├── drink_cat/
│   ├── app.py           # 应用主逻辑、托盘、定时器
│   ├── floating.py      # 浮窗 UI
│   ├── advice.py        # 联网饮水/天气建议
│   ├── store.py         # 本地存储
│   ├── theme.py         # 全局浅色主题
│   ├── tray_icon.py     # 进度托盘图标绘制
│   ├── celebration.py   # 达标庆祝文案
│   ├── win_tray.py      # Windows 托盘固定尝试（注册表/AppUserModelID）
│   └── ...
├── requirements.txt
└── requirements-build.txt
```

---

## 依赖

| 用途 | 包 |
|------|-----|
| 运行 | `PyQt6`, `requests` |
| 打包 | `pyinstaller` |

---

## 说明与限制

- **网络**：建议与天气依赖外网；部分网络下个别接口可能失败，程序会回退到本地基础建议量。
- **托盘通知**：请在系统设置中允许应用通知，否则可能看不到「喝水提醒」气泡。
- **参考地**：优先使用国内常见 IP 归属接口展示中文地区，失败时回退其它源。

---

## 开源协议（禁止商用）

本仓库采用 **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)**（简称 **PolyForm 非商业许可**），全文见仓库根目录 [`LICENSE`](LICENSE)。

**要点（非法律意见，以英文原文为准）：**

- ✅ **允许**：个人学习、研究、爱好、非营利/教育/公立科研/政府等机构的非商业使用；在许可范围内使用、修改与再分发（须附带相同许可与声明）。
- ❌ **不允许**：以**营利或商业目的**使用本软件（例如收费分发、嵌入商业产品或服务、公司内部营利性运营等，除非另行取得作者书面商业授权）。

若你需要商业授权，请通过 GitHub Issue 与维护者联系。  
可将 `LICENSE` 顶部的 `Copyright (c) 2026 DrinkCat contributors` 改为你的姓名或组织名。

---

## 贡献

欢迎 Issue / Pull Request。

若觉得有用，可以点一颗 ⭐。
