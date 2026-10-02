# M3U Helper

一个基于Flask的M3U文件处理工具，可以帮助你查看和编辑M3U播放列表。

## 功能特点

- 读取并解析M3U文件链接
- 可视化展示播放列表内容
- 支持拖拽排序播放列表项目
- 支持编辑和删除播放列表条目
- 集成 `ffprobe` 查看视频和音频属性
- 支持 master m3u8、子 m3u8 和媒体片段可用性检查
- 缺少 `ffprobe` 时回退到 `ffmpeg`，再回退到 `m3u8` 清单与片段检查
- 下载包含可用性、视频分辨率和音频信息的 HTML 报告

## 安装要求

- Python 3.10+
- FFmpeg（推荐，包含 `ffprobe`）
- 没有 FFmpeg 时，Python 回退检查仍可验证 m3u8 和媒体片段

## 使用方法

### 方法1：直接运行

1. 克隆仓库
```bash
git clone https://github.com/palfans/m3u-helper.git
cd m3u-helper
```

2. 创建并激活虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 运行应用
```bash
flask run
```

### 方法2：使用Docker

支持的架构：
- linux/amd64 (x86_64)
- linux/arm64 (aarch64)
- linux/arm/v7 (armv7)

#### 使用Docker运行

```bash
docker run -d \
  --name m3u-helper \
  -p 5000:5000 \
  palfans/m3u-helper:latest
```

#### 使用Docker Compose运行

1. 下载docker-compose.yml
```bash
wget https://raw.githubusercontent.com/palfans/m3u-helper/main/docker-compose.yml
```

2. 启动服务
```bash
docker-compose up -d
```

## 访问应用

1. 访问 http://localhost:5000
2. 输入M3U文件链接或上传本地M3U文件
3. 使用界面功能进行编辑和管理
4. 使用“检查所有视频”查看批量探测结果，使用“下载 HTML 报告”保存报告

## 探测方式

探测器按照以下顺序选择方式：

1. 系统 `ffprobe`：读取结构化 JSON，提取视频分辨率、编码、音频编码、采样率和声道。
2. 系统 `ffmpeg`：读取媒体流信息并解析视频和音频基础字段。
3. Python 回退：使用已有的 `m3u8` 与 `requests` 递归读取 master/子清单，并请求最新媒体片段。

Python 回退可以判断清单和片段是否可用；当清单缺少 `RESOLUTION` 或 `CODECS` 标签时，报告会显示未知字段。

服务默认拒绝环回地址和字面内网地址。仅在确认部署环境可信时设置 `M3U_HELPER_ALLOW_PRIVATE_URLS=1`。

## HTTP 接口

- `POST /parse`：读取 M3U/M3U8 URL 或上传文件，返回播放列表条目。
- `POST /video-info`：提交 `{ "url": "https://..." }`，返回 JSON 探测结果。
- `POST /thumbnail`：提交 `{ "url": "https://..." }`，按需返回视频首帧 JPEG；截取失败不会影响可用性判定。
- `POST /check-all`：提交 `{ "entries": [{ "title": "...", "url": "https://..." }], "workers": 1 }`，`workers` 支持 `1`、`2`、`3`、`5`，页面通过并发选择器提交；页面会按所选并发数分批提交，省略时使用服务端默认值。
- `POST /report`：提交 `{ "url": "https://..." }`，返回可下载的 HTML 报告；可用视频会尝试嵌入首帧截图。

## 开发说明

运行测试：

```bash
python -m unittest discover -s tests -v
```

### 构建Docker镜像

1. 克隆仓库
```bash
git clone https://github.com/palfans/m3u-helper.git
cd m3u-helper
```

2. 构建多架构镜像
```bash
chmod +x docker-build.sh
./docker-build.sh
```

## 许可证

MIT
