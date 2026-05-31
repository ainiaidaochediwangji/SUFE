# SUFE 校园信息聚合工具

> 上海财经大学（SUFE）校园信息聚合工具集，支持课程资料下载、就业信息追踪、成绩查询等功能。采用全异步架构，通过统一的 SSO 认证访问学校多个信息系统。
（小声逼逼，当前有在考虑写个抢课脚本[差不多弄完了等实战]，至于这部分开不开源可能看看热度咋样[怕无脑黑产]，或者看看有没有小朋友来接手项目，懂一点网络的可以带一下顺带可以继承抢课部分）
---

## 功能模块

| 模块 | 命令 | 说明 |
|------|------|------|
| **Canvas 课程下载** | `sufe canvas` | 批量下载 Canvas LMS 课程文件、模块文件、作业附件 |
| **就业信息追踪** | `sufe career` | 抓取就业网招聘信息，支持增量更新与变更检测 |
| **成绩查询** | `sufe grade` | 获取 EAMS 成绩数据，支持学期分析与 CSV 导出 |

### Canvas 课程下载

- SSO 自动登录（RSA 加密 + 滑块验证码破解）
- API + HTML 双模式获取课程列表
- 并发下载课程文件、模块文件、作业附件
- **增量更新检测**：基于文件大小 + `updated_at` 时间戳双重校验，文件内容更新时自动重新下载
- 智能去重合并，支持断点续传
- 为每个作业生成包含元数据的 HTML 页面

### 就业信息追踪

- 异步并发抓取招聘列表与详情
- 增量更新：缓存已抓取数据，仅刷新变更项
- 变更检测：自动识别新增、更新、删除的招聘信息
- 多格式导出：JSON / CSV / Excel

### 成绩查询

- 通过 EAMS 教务系统获取成绩数据
- 支持当前学期和历史成绩查询
- 自动计算加权平均绩点
- **按学期分组展示**：每学期课程按成绩从高到低排序，清晰直观
- 导出为 JSON 和 CSV 格式

---

## 项目结构

```
SUFE/
├── main.py                          # CLI 入口
├── pyproject.toml                   # 项目配置
├── requirements.txt                 # Python 依赖
├── sufe.yaml.example                # 用户配置文件模板
├── .env.example                     # 环境变量模板
├── .gitignore                       # Git 忽略规则
├── README.md                        # 本文件
│
├── sufe/                            # 核心包
│   ├── __init__.py
│   ├── __main__.py                  # python -m sufe 入口
│   ├── cli.py                       # 子命令路由
│   ├── config.py                    # 全局配置（URL、并发参数）
│   ├── user_config.py               # 用户配置文件加载器（sufe.yaml）
│   │
│   ├── auth/                        # 认证模块
│   │   ├── credentials.py           # 凭证加载
│   │   ├── session.py               # httpx 会话工厂
│   │   └── sso.py                   # SSO 登录流程
│   │
│   ├── canvas/                      # Canvas 子系统
│   │   ├── api.py                   # Canvas API 客户端
│   │   └── run.py                   # 下载流程编排
│   │
│   ├── career/                      # 就业网子系统
│   │   ├── api.py                   # 就业网 API 客户端
│   │   ├── run.py                   # 抓取流程编排
│   │   ├── state.py                 # 增量状态管理
│   │   └── export.py                # 数据导出（JSON/CSV/Excel）
│   │
│   └── grade/                       # 成绩查询子系统
│       ├── api.py                   # EAMS API 客户端
│       ├── analyze.py               # 成绩分析与展示
│       └── run.py                   # 查询流程编排
│
├── course/                          # Canvas 下载目录（运行时生成）
├── career_data/                     # 就业数据目录（运行时生成）
│   └── sxzpxx/
│       ├── cache/                   # 增量缓存
│       ├── records.json             # 招聘详情
│       ├── records.csv              # 汇总表
│       ├── positions.csv            # 岗位表
│       ├── attachments.csv          # 附件表
│       └── career_data.xlsx         # Excel 汇总
└── grade_data/                      # 成绩数据目录（运行时生成）
    ├── grades.json                  # 完整成绩数据
    └── grades.csv                   # CSV 导出
```

---

## 技术栈

| 组件 | 库 | 说明 |
|------|-----|------|
| HTTP 客户端 | `httpx` | 异步 HTTP/2 支持，连接池复用 |
| 异步存储 | `aiofiles` | 异步文件 I/O |
| 并发控制 | `asyncio.Semaphore` | 分级并发限制 |
| 进度展示 | `tqdm` | 下载/抓取进度条 |
| HTML 解析 | `beautifulsoup4` | EAMS 成绩页面解析 |
| 配置解析 | `pyyaml` | YAML 配置文件加载 |
| Excel 导出 | `openpyxl` | 就业数据多 Sheet 导出 |
| 密码加密 | `pycryptodome` | RSA 加密 SSO 密码 |
| 环境变量 | `python-dotenv` | .env 文件解析 |

**并发配置**（`config.py`）：

- Canvas 课程并发：`CANVAS_COURSE_CONCURRENCY = 2`
- Canvas 文件并发：`CANVAS_FILE_CONCURRENCY = 4`
- Canvas 模块发现并发：`CANVAS_MODULE_CONCURRENCY = 8`
- 就业详情并发：`CAREER_CONCURRENCY = 8`
- 就业分页并发：`CAREER_PAGE_CONCURRENCY = 3`

---

## 快速开始

### 1. 安装依赖

```bash
pip install -e .
# 或
pip install -r requirements.txt
```

### 2. 配置账号

```bash
cp .env.example .env
```

编辑 `.env`：

```env
user=学号
pwd=密码
```

> `.env` 已加入 `.gitignore`，不会被提交。

### 3. 运行

```bash
# Canvas 课程下载
python -m sufe canvas

# 就业信息抓取
python -m sufe career

# 成绩查询与分析
python -m sufe grade

# 查看帮助
python -m sufe --help
```

### 4. 自定义参数

各模块支持命令行参数指定输出目录和并发配置：

```bash
# Canvas 下载到指定目录，并发数调整为 4
python -m sufe canvas --output /path/to/courses --concurrency 4

# 就业信息抓取，限制最大条目数
python -m sufe career --output /path/to/career --max-items 500

# 成绩数据保存到指定目录
python -m sufe grade --output /path/to/grades
```

**完整参数列表：**

| 模块 | 参数 | 说明 | 默认值 |
|------|------|------|--------|
| `canvas` | `--output`, `-o` | 输出目录 | `config.py: DOWNLOAD_DIR` |
| `canvas` | `--concurrency`, `-c` | 并发下载课程数 | `config.py: CANVAS_COURSE_CONCURRENCY` |
| `career` | `--output`, `-o` | 输出目录 | `config.py: CAREER_DIR` |
| `career` | `--concurrency`, `-c` | 并发详情抓取数 | `config.py: CAREER_CONCURRENCY` |
| `career` | `--page-concurrency` | 并发分页抓取数 | `config.py: CAREER_PAGE_CONCURRENCY` |
| `career` | `--max-items` | 最大抓取条目数 | `config.py: CAREER_MAX_ITEMS` |
| `grade` | `--output`, `-o` | 输出目录 | `config.py: GRADE_DIR` |

> 默认值均可在 `sufe/config.py` 中修改。

### 5. 配置文件（推荐）

复制示例配置文件并按需修改：

```bash
cp sufe.yaml.example sufe.yaml
```

编辑 `sufe.yaml`：

```yaml
# Canvas 模块配置
canvas:
  output_dir: course          # 输出目录（相对于项目根目录）
  concurrency: 2              # 并发下载课程数
  file_concurrency: 4         # 文件下载并发数
  module_concurrency: 8       # 模块发现并发数

# Career 模块配置
career:
  output_dir: career_data/sxzpxx
  concurrency: 8              # 详情抓取并发数
  page_concurrency: 3         # 分页抓取并发数
  max_items: 300              # 最大抓取条目数

# Grade 模块配置
grade:
  output_dir: grade_data
  export_formats:             # 导出格式
    - json
    - csv
  generate_report: true       # 是否生成分析报告
```

**配置优先级：** CLI 参数 > `sufe.yaml` > `config.py` 默认值

> `sufe.yaml` 已加入 `.gitignore`，不会被提交到版本控制。

---

## Canvas 下载目录结构

```
course/
├── 课程名称A/
│   ├── files/                         # 课程文件区
│   ├── modules/                       # 模块区
│   ├── assignments/                   # 作业
│   │   └── 作业名称/
│   │       ├── assignment.html        # 作业元数据
│   │       └── attachments/           # 作业附件
│   └── _download_report.json          # 下载报告（增量更新依据）
│
└── 学科代码/                          # 当学科代码与课程名不同时
    └── 课程名称B/
        ├── files/
        ├── modules/
        ├── assignments/
        └── _download_report.json
```

### 增量更新机制

Canvas 模块采用**双重校验**检测文件更新：

1. **文件大小对比**：本地文件大小与 API 返回的 `size` 字段对比
2. **更新时间对比**：读取上次的 `_download_report.json`，对比 API 返回的 `updated_at` 时间戳

| 场景 | 文件大小 | updated_at | 行为 |
|------|---------|------------|------|
| 文件不存在 | - | - | 下载 |
| 文件未变化 | 相同 | 相同 | 跳过 |
| 文件大小变化 | 不同 | 任意 | 重新下载 |
| 文件内容更新（大小不变） | 相同 | 不同 | 重新下载 |
| 文件内容更新（大小变化） | 不同 | 不同 | 重新下载 |

> `_download_report.json` 记录了每个文件的 `id`、`updated_at`、`size` 等元数据，作为下次运行的对比基准。

---

## 注意事项

1. **网络环境**：需在校园网或 VPN 环境下访问学校系统
2. **下载目录**：默认下载到 `course/`，确保磁盘空间充足
3. **滑块验证**：Canvas 登录采用暴力扫描策略，如学校升级验证码机制可能需要调整
4. **增量更新**：
   - Canvas 模块基于文件大小 + 更新时间双重校验，自动重新下载更新过的文件
   - 就业信息模块会缓存已抓取数据，重复运行时仅刷新变更项
5. **并发控制**：各模块已配置合理的并发限制，避免对服务器造成压力
6. **Windows 终端**：成绩查询时建议设置 `PYTHONIOENCODING=utf-8` 以正确显示中文

---

## 扩展新模块

添加新的学校系统（如图书馆系统）：

1. 在 `sufe/` 下创建子目录，如 `sufe/library/`
2. 实现 `api.py`：封装该系统的 API 调用
3. 实现 `run.py`：编排完整流程（登录 → 抓数据 → 导出）
4. 如需增量更新，添加 `state.py`
5. 如需特殊导出格式，添加 `export.py`
6. 在 `cli.py` 中注册子命令
7. 在 `config.py` 中添加相关配置常量
8. 在 `user_config.py` 中添加配置加载函数

所有模块共享 `auth/` 中的 SSO 认证能力，无需重复实现登录逻辑。

---

## 开源许可

本项目采用 [MIT License](LICENSE) 开源许可。

---

## 免责声明

### 使用范围

本工具仅供上海财经大学**在读师生个人学习备份**使用，目的是方便用户在本地整理、复习课程资料及追踪就业信息。工具本身不存储、不缓存、不中转任何内容，所有数据均直接从学校官方平台下载至用户本地设备。

### 禁止行为

| 禁止行为 | 说明 |
|----------|------|
| 未经授权分发 | 将下载的课程资料上传至公开网盘、论坛、社交媒体或分享给非本课程选课人员 |
| 商业用途 | 将课程内容用于售卖、培训、出版等营利性活动 |
| 批量爬取公开 | 利用本工具批量抓取课程内容后公开发布或建立镜像站点 |
| 账号共享 | 将本工具或账号借予他人使用，导致非授权人员获取课程资料 |
| 干扰平台 | 修改并发配置、高频请求等可能对学校服务器造成压力的操作 |
| 平台攻击 | 对学校 SSO、Canvas、就业网或任何其他校内系统进行渗透测试、漏洞扫描、DDoS 攻击 |
| 逆向滥用 | 拆解、修改本工具代码后用于攻击学校系统或爬取非授权数据 |
| 数据滥用 | 利用本工具获取的账号凭证、课程信息、师生资料等进行任何形式的二次利用 |

### 知识产权

- 使用本工具下载的所有课程内容（课件、讲义、视频、作业、试卷等）的**知识产权归原授课教师或学校所有**
- 本工具仅提供技术层面的下载功能，不对任何课程内容的准确性、完整性、合法性负责
- 用户应自行判断下载内容的版权状态，并遵守《中华人民共和国著作权法》及学校相关规定

### 账号与隐私

- 用户的学号、密码仅保存在本地 `.env` 文件中，**不会上传至任何第三方服务器**
- 请妥善保管 `.env` 文件，避免账号信息泄露
- 因用户个人原因（账号共享、密码泄露）导致的任何损失，由用户自行承担

### 网络安全

本工具的所有网络请求均**仅限于**上海财经大学官方域名（`login.sufe.edu.cn`、`canvas.shufe.edu.cn`、`career.sufe.edu.cn`、`eams.sufe.edu.cn` 等），不会向任何第三方服务器发送数据。用户**不得**：

- 修改代码将请求指向非学校官方域名
- 利用本工具的网络请求逻辑对学校其他信息系统进行探测或攻击
- 将本工具作为网络攻击工具的一部分使用

### 法律合规

使用本工具须遵守以下法律法规：

- 《中华人民共和国网络安全法》
- 《中华人民共和国数据安全法》
- 《中华人民共和国个人信息保护法》
- 《中华人民共和国著作权法》
- 《上海财经大学校园网络安全管理办法》及相关校规校纪

### 责任限制

本工具按「**原样**」提供，开发者不对以下情况承担责任：

- 因学校平台升级、接口变更导致工具无法使用
- 因网络中断、服务器故障导致下载失败或文件损坏
- 因用户违反本免责声明或相关法律法规而产生的任何法律后果
- 因用户修改代码、绕过限制或滥用工具导致的账号封禁、纪律处分或法律责任

**下载及使用本工具即视为您已阅读并同意本免责声明的全部内容。**
