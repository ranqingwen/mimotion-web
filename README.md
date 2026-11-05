# mimotion-web

小米运动（Zepp Life）自动刷步数 —— 本地 Docker 自托管版，带 Web 管理界面。

不再依赖 GitHub Actions，在自己服务器/NAS 上用 Docker 一键部署，网页里配置账号即可长期自动运行。

> 核心刷步逻辑来自 [TonyJiangWJ/mimotion](https://github.com/TonyJiangWJ/mimotion)（Apache-2.0 License），本项目在其基础上封装了 Web 管理界面与 Docker 化部署，特此感谢。

---

## ✨ 功能特性

- **Web 管理界面**：账号密码登录（带 CSRF 防护 + 登录失败锁定），适合公网部署
- **账号动态管理**：「新增账号」逐行添加账号/密码（支持明文切换查看、单行删除），多账号自动用 `#` 分隔传给核心逻辑，无需手动拼接
- **步数模式（二选一）**：
  - 🏃 **范围随机**：在最小/最大步数间随机；可选「随时间线性递增」——填写的范围为北京时间 22:00 达到的峰值，更早执行按当前时间占比缩放（模拟真人一天步数逐渐累积）
  - 🎯 **固定步数**：每次执行都设为确切值，适合实时把步数改成某个目标值（此模式下每天执行时间只能填一个时间点）
- **定时调度**：按北京时间执行，与服务器时区无关；每个时间点在 0~59 分钟内随机执行，执行完自动重新随机，避免固定时间被风控
- **执行控制**：仅保存（等定时执行）/ 保存并立即执行一次 / 取消自动执行 / 重新随机执行时间，状态持久化，重启不丢
- **执行日志**：网页内查看最近 50 次执行记录（成功/失败、随机步数、接口返回）
- **推送通知（可选）**：PushPlus / 企业微信 Webhook / Telegram
- **Token 缓存**：配置 16 位 AES_KEY 后加密缓存登录 token，避免频繁登录触发 429

## 🖼️ 界面预览

| 登录页 | 管理后台 |
| --- | --- |
| ![登录页](docs/login.png) | ![管理后台](docs/dashboard.png) |
| 深色登录页，账号密码校验 | 配置账号、步数、调度、推送，查看执行日志 |

## 🚀 快速开始（Docker Compose）

```bash
# 1. 克隆仓库
git clone https://github.com/ranqingwen/mimotion-web.git
cd mimotion-web

# 2. 修改 docker-compose.yml 中的 WEB_USER / WEB_PASS（公网部署必改！）

# 3. 构建并启动
docker compose up -d --build
```

### docker-compose.yml 完整内容

仓库根目录自带 `docker-compose.yml`，内容如下（可直接复制使用，改好用户名密码即可）：

```yaml
services:
  mimotion-web:
    build: .            # 使用项目目录下的 Dockerfile 构建镜像
    container_name: mimotion-web
    restart: unless-stopped
    ports:
      - "8000:8000"     # 左边是宿主机端口，可自行修改
    environment:
      - WEB_USER=admin        # ⚠️ Web 登录用户名，公网部署必改
      - WEB_PASS=admin123     # ⚠️ Web 登录密码，公网部署必改
      - TZ=Asia/Shanghai      # 时区
    volumes:
      - ./data:/app/data      # 数据持久化：配置、日志、加密 token 都在这里
```

> 说明：`build: .` 需要构建上下文（即本项目目录）。所有配置在网页里填写并保存后存于 `data/config.json`，容器重建不丢失。

### 使用预构建镜像（ghcr.io，部署最快）

项目通过 GitHub Actions 自动构建并发布镜像到 GitHub Container Registry，直接拉取即可，**无需在服务器上构建**（首次可用）：

```yaml
services:
  mimotion-web:
    image: ghcr.io/ranqingwen/mimotion-web:latest
    container_name: mimotion-web
    restart: unless-stopped
    ports:
      - "8000:8000"     # 左边是宿主机端口，可自行修改
    environment:
      - WEB_USER=admin        # ⚠️ Web 登录用户名，公网部署必改
      - WEB_PASS=admin123     # ⚠️ Web 登录密码，公网部署必改
      - TZ=Asia/Shanghai      # 时区
    volumes:
      - ./data:/app/data      # 数据持久化（位于编排工作目录下，可用绝对路径指定）
```

```bash
docker compose pull && docker compose up -d   # 拉取镜像并启动，几秒完成
```

> 提示：首次发布后镜像默认为**私有**，需到 GitHub → 头像 → Packages → `mimotion-web` → Package settings → Change visibility 设为 **Public**，他人（包括你的服务器）才能免登录拉取。

### 从 GitHub 拉取构建（免上传文件）

Compose 的 `build:` 支持直接指向 Git 仓库。用 `docker compose` 命令行或任何支持 Compose 编排的环境（NAS 的 Container Manager、可视化容器工具等），将以下内容保存为 `docker-compose.yml` 并启动即可，机器上不需要有任何项目文件（需先确认仓库已公开）：

```yaml
services:
  mimotion-web:
    build: https://github.com/ranqingwen/mimotion-web.git#main
    container_name: mimotion-web
    restart: unless-stopped
    ports:
      - "8000:8000"     # 左边是宿主机端口，可自行修改
    environment:
      - WEB_USER=admin        # ⚠️ Web 登录用户名，公网部署必改
      - WEB_PASS=admin123     # ⚠️ Web 登录密码，公网部署必改
      - TZ=Asia/Shanghai      # 时区
    volumes:
      - ./data:/app/data      # 数据持久化（位于编排工作目录下，可用绝对路径指定）
```

- `#main` 表示使用 main 分支；Docker 会自动 clone 仓库并按 Dockerfile 构建
- 后续更新代码后，重新执行 `docker compose up -d --build`（或在你的容器管理工具里点「重建」）即可拉取最新代码
- 数据卷 `./data` 相对于编排工作目录，建议改为绝对路径（如 `/opt/mimotion-data:/app/data`）方便备份

### 手动构建镜像方式（适用于无法使用构建上下文的场景）

```bash
docker build -t mimotion-web .
```

然后把上面 compose 中的 `build:` 替换为 `image: mimotion-web` 即可。

访问 `http://服务器IP:8000`，使用 `WEB_USER` / `WEB_PASS` 登录。

## 🧩 更多部署方式（NAS / 可视化工具 / 命令行通用）

只要环境里有 Docker（或 Docker Compose），以下写法都通用：

**方式一：预构建镜像 / Compose 从 GitHub 拉取（免上传文件）**

- 用上面「使用预构建镜像」的 yaml（`image: ghcr.io/...`，拉取即用，最快）
- 或用「从 GitHub 拉取构建」的 yaml（`build: 仓库地址`，在本地构建）

改好 `WEB_USER` / `WEB_PASS` 后：

- 命令行：`docker compose up -d --build`
- NAS（群晖 Container Manager、威联通 Container Station 等）：导入该 yaml 创建项目/应用即可
- 其他可视化容器工具：用「自定义 compose/编排」功能粘贴部署

**方式二：上传项目文件 + 本地构建**

1. 将仓库 zip 上传到服务器（如 `/opt`）并解压，得到含 `docker-compose.yml` 的目录
2. 修改 `docker-compose.yml` 中的 `WEB_USER` / `WEB_PASS`
3. 在该目录执行 `docker compose up -d --build`（或在可视化工具中选择该路径创建编排，`build: .` 需要构建上下文）

**通用建议**：
- 防火墙及云服务器安全组放行 `8000` 端口后访问 `http://服务器IP:8000`
- 用 Nginx 反向代理等套一层 HTTPS
- 定期备份 `data` 数据目录（所有配置、日志、token 都在里面）

## ⚙️ 配置说明

### 环境变量（docker-compose.yml）

| 变量 | 说明 |
| --- | --- |
| `WEB_USER` | Web 登录用户名（默认 `admin`，**公网必改**） |
| `WEB_PASS` | Web 登录密码（默认 `admin123`，**公网必改**） |
| `TZ` | 时区，默认 `Asia/Shanghai` |

### 网页配置项

| 配置 | 说明 |
| --- | --- |
| 账号 / 密码 | 小米运动（Zepp Life）账号，**不是小米账号**；手机号或邮箱；支持多账号，逐行添加 |
| 最小/最大步数 | 范围随机模式下使用；勾选「随时间线性递增」时代表 22:00 的峰值 |
| 固定步数 | 固定步数模式下使用，每次执行设为该值 |
| 每天执行时间 | 北京时间 0-23 点，逗号分隔（如 `9,12,15,18,20,22`）；固定步数模式只能填一个 |
| AES_KEY | 可选，16 个字符；配置后加密缓存登录 token，避免频繁登录 429 |
| 推送配置 | PushPlus Token / 企业微信 Webhook Key / Telegram Bot Token + Chat ID，均可选 |

## 🔒 公网部署安全建议

- 务必修改 `WEB_USER` / `WEB_PASS`，不要使用默认值
- 建议通过 Nginx 反向代理等套一层 HTTPS 访问
- 登录接口带 CSRF 校验与失败锁定（5 次失败锁 2 分钟）
- 所有敏感数据仅保存在服务器本地 `data` 目录，不上传任何第三方

## ❓ 常见问题

- **提示登录失败 / 401**：确认账号是 Zepp Life（小米运动）账号，不是小米账号；密码错误可多试几次
- **支付宝没有同步步数**：到小米运动 App → 设置 → 账号 → 注销账号（清空数据）后重新登录、重新绑定第三方；注意小米运动本身不显示刷的步数，只有关联的第三方会同步
- **429 限流**：同 IP 登录过多账号可能触发；配置 AES_KEY 缓存 token 可显著缓解
- **步数不对**：检查是否处于「范围随机 + 随时间递增」模式——非 22:00 执行时步数会按比例缩放，属正常现象；想固定就切「固定步数」模式

## ⚠️ 免责声明

本项目仅供学习交流使用，请勿用于任何商业或非法用途。使用本项目产生的一切后果由使用者自行承担，与作者无关。刷步数行为可能违反小米运动（Zepp Life）用户协议，请自行评估风险，账号被封禁等问题概不负责。

## 🙏 致谢

- 核心刷步逻辑：[TonyJiangWJ/mimotion](https://github.com/TonyJiangWJ/mimotion)（Apache-2.0），其又基于 [xunichanghuan/mimotion](https://github.com/xunichanghuan/mimotion) 与 [huangshihai/mimotion](https://github.com/huangshihai/mimotion)
- 登录接口 AES 加密密钥参考：[hanximeng/Zepp_API](https://github.com/hanximeng/Zepp_API)
- 本项目新增部分（Web 界面、调度、Docker 化）：[ranqingwen](https://github.com/ranqingwen)

## 📄 License

[Apache-2.0](LICENSE)（沿用上游协议）
