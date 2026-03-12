# Linux 主机监控 (monitor_hosts)

基于 **Python 2.7** 的 Linux 监控脚本，适用于当前项目 `py2.7.18` 环境。仅使用标准库与 `/proc`，无需额外依赖。

## 监控项

| 指标 | 说明 | 配置项 |
|------|------|--------|
| **CPU** | 使用率（两次采样 /proc/stat） | `cpu.warn_percent`, `cpu.interval_sec` |
| **内存** | 使用率（/proc/meminfo） | `memory.warn_percent` |
| **磁盘** | 指定挂载点使用率（statvfs） | `disk.warn_percent`, `disk.mounts` |
| **文件完整性** | 关键目录文件变更（新增/删除/修改） | `file_integrity.watch_dirs`, `baseline_path` |
| **进程** | 期望存在的进程名是否在运行 | `process.expected_names`, `process.must_running` |
| **端口** | 期望监听的端口是否在 LISTEN | `port.expected_ports` |

## 目录结构

```
项目根目录（py2.7.18）/
  monitor_hosts/
    data/                    # 监控数据目录（自动创建）
      monitor_hosts.db       # SQLite：配置与运行记录
    __init__.py
    config.py                # 配置加载（优先从 monitor_hosts/data/*.db 读写）
    db.py                    # SQLite 初始化与 config/run 表
    monitor_config.json      # 可选示例/备份，未用 DB 时可指定路径读
    main.py                  # 入口
    run_web.py               # 启动 Web 配置界面
    runner.py                # 运行器：调度各采集器、汇总告警
    remote.py                # 远程采集：SSH 到目标机执行 main.py --json
    web/
      app.py               # Flask 后端（配置 API + 执行监控）
      requirements.txt     # Web 依赖：Flask 1.1.2
      templates/
        index.html         # 配置页
      static/
    collectors/
      __init__.py
      cpu.py               # CPU 使用率
      memory.py            # 内存使用率
      disk.py              # 磁盘使用率
      file_integrity.py    # 文件完整性
      process.py           # 进程名检查
      port.py              # 端口监听检查
    README.md
```

## 使用方式

### 1. 使用项目虚拟环境

```bash
cd /path/to/py2.7.18
source menv/bin/activate
python monitor_hosts/main.py
```

### 2. 配置与 SQLite 存储

- **配置与监控阈值** 保存在 **monitor_hosts/data/monitor_hosts.db**（SQLite）。
- 若 **monitor_hosts/data** 目录或 **monitor_hosts.db** 不存在，**首次加载配置或重启项目时会自动创建** data 目录、数据库文件及表结构（`config`、`monitor_runs`）。
- 未保存过配置时使用代码内默认配置；Web 或后续保存会写入 SQLite。
- 仍支持通过 `--config 某路径.json` 从 JSON 文件读取配置（兼容旧用法）。

**SQLite 表结构（自动创建）：**

- **config**：`key`（如 `current`）、`value`（完整配置 JSON）、`updated_at`。当前使用的配置与阈值存于 `key='current'`。
- **monitor_runs**：可选记录每次运行的 `run_at`、`alerts`、`results`（JSON），便于后续扩展历史查询。

```bash
# 使用默认存储（SQLite）
python monitor_hosts/main.py

# 指定 JSON 文件读配置（不写 SQLite）
python monitor_hosts/main.py --config monitor_hosts/monitor_config.json
```

### 3. 输出 JSON（便于对接告警或监控平台）

```bash
python monitor_hosts/main.py --json
```

### 4. 建立文件完整性基线（首次或重置）

需先配置 `file_integrity.watch_dirs` 和 `file_integrity.baseline_path`，然后执行：

```bash
python monitor_hosts/main.py --build-baseline
```

之后每次 `main.py` 运行时会与基线比对，有新增/删除/修改则产生告警。

### 5. 定时执行（cron）

```bash
# 每 5 分钟跑一次，日志落盘
*/5 * * * * /path/to/py2.7.18/menv/bin/python /path/to/py2.7.18/monitor_hosts/main.py >> /var/log/monitor_hosts.log 2>&1
```

### 6. 监控目标列表与远程采集（中心机 SSH）

- **运行模式** 在配置中通过 **target_hosts** 指定：
  - **local**（默认）：在本机执行采集，监控本机。
  - **remote**：在**中心机**上运行脚本，通过 **SSH 连接配置中的每台目标主机**，在目标机上执行 `python monitor_hosts/main.py --json`，取回 JSON 后汇总告警与结果。
- **配置项**（存于 SQLite / Web 页「监控目标」）：
  - **target_hosts.mode**：`local` 或 `remote`。
  - **target_hosts.hosts**：列表，每项 `{ "host", "port", "user", "key_file", "config_override" }`。**新增目标时默认使用左侧默认配置**；可为某目标单独设置 **config_override**（覆盖项），执行时该目标使用「默认配置 + config_override」合并后的配置（中心机通过 stdin 传给目标机 `main.py --config-stdin`）。
  - **target_hosts.remote_project_path**、**remote_command**、**ssh_timeout**：同上。
- **Web 使用流程**：左侧导航为 **监控概览**、**增加服务器**、**服务器监控项**。在「增加服务器」中：先选择运行模式与远程选项，再通过「+ 添加目标」增加目标机器（主机、端口、用户、密钥文件），对每行可点击「执行监控」单独执行该主机监控、或「关联指标」配置覆盖项（CPU、内存、磁盘、文件完整性、进程、端口等）、或「删除」。修改后需在左侧点击「保存配置」生效。
- **前置条件**：
  - 中心机可免密或密钥登录各目标主机。
  - 目标机已部署 monitor_hosts；中心机将合并后的配置通过 stdin 传给目标机时，目标机需支持 `python main.py --json --config-stdin`。

## 配置说明（monitor_config.json / SQLite）

- **monitoring_enabled**（默认 true）：总开关。为 false 时**不执行任何监控采集**（命令行、cron、Web「执行一次监控」均跳过采集）；仍可登录 Web 后台查看、修改所有配置。关闭后仅做配置管理。
- **cpu.warn_percent**: CPU 使用率超过该值告警（默认 85）。**cpu.enabled** 可关闭该项。
- **memory.warn_percent**: 内存使用率超过该值告警。**memory.enabled** 可关闭。
- **disk.mounts**: 需要检查的挂载点列表；**disk.warn_percent** 超过即告警。**disk.enabled** 可关闭。
- **file_integrity**: **watch_dirs**、**baseline_path**、**exclude_patterns**；**enabled** 可关闭。资源相关：**use_mtime_only**（只比 mtime+size）、**hash_only_if_changed**、**max_file_size_to_hash**、**max_files**、**max_depth**（见上节）。
- **process**: **expected_names**、**must_running**；**enabled** 可关闭。**use_light_check: true** 时仅用 pgrep/ps -C，不遍历 /proc。
- **port.expected_ports**: 期望处于监听状态的端口列表。**port.enabled** 可关闭。
- **target_hosts**: **mode**、**hosts**（每项可含 **config_override**，用于该目标覆盖默认配置）、**remote_project_path**、**remote_command**、**ssh_timeout**。新增目标默认关联默认配置；在 Web 上可为每个目标点「配置」单独设置覆盖项。
- **alerts_notify**：告警通知。**enabled** 为 true 时，每次产生告警后会向已启用的渠道发送消息。
  - **telegram**：**enabled**、**bot_token**（@BotFather 获取）、**chat_id**（群组 ID，将机器人拉入群后通过 getUpdates 或工具获取）。通过 Telegram Bot API 发送群组消息。
  - **lark**：**enabled**、**webhook_url**（飞书/Lark 群机器人 webhook 地址）。在群设置 → 群机器人 → 自定义机器人中复制 webhook 即可。

按实际环境修改 `expected_names`、`expected_ports`、`mounts`、`watch_dirs` 等即可。

## 资源优化设计（降低被监控端损耗）

为减少在被监控主机上的 CPU、内存与 IO 占用，做了如下设计，可通过配置调节：

| 机制 | 说明 | 配置项 |
|------|------|--------|
| **按项开关** | 不需要的监控项可关闭，减少采集与 IO | 各段 `enabled: true/false`（如 `cpu.enabled`） |
| **文件完整性** | 先比 mtime+size，仅变更时再哈希；大文件可不哈希或只哈希前 N 字节 | `use_mtime_only`、`hash_only_if_changed`、`max_file_size_to_hash`、`max_files`、`max_depth` |
| **进程检查** | 仅查询期望进程名是否存在，不遍历全量 /proc | `process.use_light_check: true`（默认） |

- **file_integrity**
  - **use_mtime_only**: 为 true 时只比较 mtime/size，不做任何读文件哈希，IO 最小。
  - **hash_only_if_changed**: 为 true（默认）时仅当 mtime 或 size 与基线不同才计算哈希，避免每次全量读文件。
  - **max_file_size_to_hash**: 超过该字节数的文件不计算哈希（默认 1048576=1MB），仅用 mtime+size 判断。
  - **max_files** / **max_depth**: 限制参与检查的文件数量与目录深度，避免超大目录拖垮单次执行。

- **process**
  - **use_light_check**: 为 true（默认）时使用 `pgrep -x` / `ps -C` 只查配置中的进程名，不执行 `ps -eo comm` 且不遍历 `/proc/*/cmdline`。

建议在资源紧张或监控目录很大的主机上：将 **file_integrity** 设为 `use_mtime_only: true`，或设置 **max_files** / **max_file_size_to_hash**；不需要的监控项设 **enabled: false**。

## Web 配置界面

通过浏览器配置监控指标、保存配置并执行一次检测。

### 安装 Web 依赖（仅首次）

```bash
cd /path/to/py2.7.18
source menv/bin/activate
pip install -r monitor_hosts/web/requirements.txt
```

### 启动 Web 服务

```bash
python monitor_hosts/run_web.py --host 0.0.0.0 --port 5000
```

浏览器访问 **http://服务器IP:5000/** 即可使用：

- **监控概览（首页）**：展示上次执行时间、告警数、服务器数；最近一次监控结果按主机以卡片形式展示（CPU、内存、磁盘、进程、端口、文件完整性等）。可在此执行一次监控或仅建立文件基线，执行结果会写入 SQLite 并在首页展示。
- **增加服务器**：维护目标机器列表（IP、端口、用户、私钥文件）；每行支持「执行监控」（对该机执行一次并跳转概览查看结果）、「关联指标」（为该机配置覆盖项）、「删除」。
- **服务器监控项**：配置默认监控项（CPU、内存、磁盘使用、系统文件篡改、多端口、多进程等）；新增加的服务器将使用此默认配置，单机可在「增加服务器」中通过「关联指标」覆盖。
- **保存配置**：修改任意配置后点击左侧「保存配置」，会写入 **monitor_hosts/data/monitor_hosts.db**（SQLite），与命令行 `main.py` 共用同一份配置（未指定 `--config` 时从 SQLite 读取）。

命令行执行的 `main.py` 与 Web 默认使用同一份 SQLite 配置（**monitor_hosts/data/monitor_hosts.db**）；保存后对两者均生效。

## 依赖与运行环境

- **命令行监控**：仅使用 **Python 2.7 标准库**，无需 pip 安装。
- **Web 界面**：需安装 `monitor_hosts/web/requirements.txt`（Flask 1.1.2 等，兼容 Python 2.7）。
- **目标环境为 Linux**：CPU、内存、端口等依赖 `/proc`，在 macOS/Windows 上会报错或跳过，属正常。文件完整性、磁盘在 macOS 上也可部分运行。
- 若将日志写到 `/var/log` 或 `/var/lib`，需相应写权限（或修改配置为当前用户可写路径）。

## 退出码

- `0`: 所有检查通过，无告警。
- `1`: 存在告警或采集异常。
