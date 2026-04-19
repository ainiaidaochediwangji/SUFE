# SUFE Canvas 课程资料自动下载工具

> 上海财经大学（SUFE）Canvas LMS 课程资料批量下载器，支持单点登录（SSO）自动认证、滑块验证码破解、课程文件/作业附件全量抓取。

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **SSO 自动登录** | 自动完成学校统一身份认证，包括 RSA 密码加密和滑块验证码破解 |
| **课程列表获取** | 通过 Canvas API 或 HTML 页面双模式获取课程列表 |
| **文件全量下载** | 下载课程文件、模块文件、作业描述中的附件 |
| **智能去重合并** | 合并来自不同来源（文件区/模块区）的同一文件 |
| **作业信息归档** | 为每个作业生成包含元数据的 HTML 页面 |
| **断点续传兼容** | 已下载文件自动跳过，支持文件大小校验 |

---

## 目录结构

```
SUFE/
├── main.py                 # 程序入口
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量配置模板
├── .gitignore              # Git 忽略规则
├── README.md               # 本文件
├── course/                 # 下载的课程资料（运行后生成）
└── src/
    ├── config.py           # URL、请求头等全局配置
    ├── sso.py              # SSO 登录与滑块验证码处理
    ├── canvas_client.py    # Canvas API 交互与文件下载
    └── fs_utils.py         # 文件系统工具
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置账号

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的学号和密码：

```env
user=5201314
pwd=你的密码
```

> `.env` 已加入 `.gitignore`，不会被提交到版本控制，请放心使用。

### 3. 运行

```bash
python main.py
```

### 输出示例

```
[1/4] Logging into SUFE SSO...
[2/4] Establishing Canvas session...
Canvas authenticated at: https://canvas.shufe.edu.cn/
[3/4] Fetching course list...
Found 12 courses
[4/4] Downloading course materials...
[1/12] 高级计量经济学
[2/12] 公司金融
...
Done
Courses: 12
Course failures: 0
Discovered: 156
Downloaded: 23
Skipped: 133
Failed: 0
```

---

## 下载目录结构

下载的文件按课程组织：

```
course/
├── 课程名称A/              # 当学科代码与课程名相同时，直接以课程名作为文件夹
│   ├── files/              # 课程文件区（按 Canvas 文件夹层级分子目录）
│   ├── modules/            # 模块区（按模块名分子文件夹）
│   └── assignments/        # 作业
│       └── 作业名称/
│           ├── assignment.html      # 作业元数据页面
│           └── attachments/         # 作业附件
│
└── 学科代码/               # 当学科代码与课程名不同时，增加学科层级
    └── 课程名称B/
        ├── files/
        ├── modules/
        └── assignments/
```

---

## 依赖

| 包名 | 用途 |
|------|------|
| `requests` | HTTP 会话管理与文件下载 |
| `python-dotenv` | `.env` 配置文件读取 |
| `pycryptodome` | RSA 密码加密 |

---

## 注意事项

1. **下载目录**：默认下载到 `course/`，确保磁盘空间充足
2. **网络环境**：需要在校园网或 VPN 环境下访问 Canvas
3. **滑块验证**：当前采用暴力扫描策略，如学校升级验证码机制可能需要调整

---

## 开源许可

本项目采用 [MIT License](LICENSE) 开源许可。

```
MIT License

Copyright (c) 2025 SUFE Canvas Downloader Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 免责声明

### 使用范围

本工具仅供上海财经大学**在读师生个人学习备份**使用，目的是方便用户在本地整理、复习课程资料。工具本身不存储、不缓存、不中转任何课程内容，所有数据均直接从学校官方 Canvas 平台下载至用户本地设备。

### 禁止行为

使用本工具时，**严禁**从事以下行为：

| 禁止行为 | 说明 |
|----------|------|
| 未经授权分发 | 将下载的课程资料上传至公开网盘、论坛、社交媒体或分享给非本课程选课人员 |
| 商业用途 | 将课程内容用于售卖、培训、出版等营利性活动 |
| 批量爬取公开 | 利用本工具批量抓取课程内容后公开发布或建立镜像站点 |
| 账号共享 | 将本工具或账号借予他人使用，导致非授权人员获取课程资料 |
| 干扰平台 | 高频请求、多线程并发等可能对 Canvas 服务器造成压力的操作 |
| 平台攻击 | 对学校 SSO、Canvas 或任何其他校内系统进行渗透测试、漏洞扫描、DDoS 攻击或任何破坏性操作 |
| 逆向滥用 | 拆解、修改本工具代码后用于攻击学校系统或爬取非授权数据 |
| 数据滥用 | 利用本工具获取的账号凭证、课程信息、师生资料等进行任何形式的二次利用或数据挖掘 |

### 知识产权

- 使用本工具下载的所有课程内容（包括但不限于课件、讲义、视频、作业、试卷等）的**知识产权归原授课教师或学校所有**。
- 本工具仅提供技术层面的下载功能，不对任何课程内容的准确性、完整性、合法性负责。
- 用户应自行判断下载内容的版权状态，并遵守《中华人民共和国著作权法》及学校相关规定。

### 账号与隐私

- 用户的学号、密码仅保存在本地 `.env` 文件中，**不会上传至任何第三方服务器**。
- 请妥善保管 `.env` 文件，避免账号信息泄露。
- 因用户个人原因（如账号共享、密码泄露）导致的任何损失，由用户自行承担。

### 网络安全

本工具的所有网络请求均**仅限于**上海财经大学官方域名（`login.sufe.edu.cn`、`canvas.shufe.edu.cn` 等），不会向任何第三方服务器发送数据。用户**不得**：

- 修改代码将请求指向非学校官方域名
- 利用本工具的网络请求逻辑对学校其他信息系统（如教务系统、图书馆系统、财务系统等）进行探测或攻击
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

- 因学校 Canvas 平台升级、接口变更导致工具无法使用
- 因网络中断、服务器故障导致下载失败或文件损坏
- 因用户违反本免责声明或相关法律法规而产生的任何法律后果
- 因用户修改代码、绕过限制或滥用工具导致的账号封禁、纪律处分或法律责任

**下载及使用本工具即视为您已阅读并同意本免责声明的全部内容。**
