# M3U Helper

一个基于Flask的M3U文件处理工具，可以帮助你查看和编辑M3U播放列表。

## 功能特点

- 读取并解析M3U文件链接
- 可视化展示播放列表内容
- 支持拖拽排序播放列表项目
- 支持编辑和删除播放列表条目
- 集成ffmpeg查看视频属性

## 安装要求

- Python 3.10+
- FFmpeg

## 安装步骤

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

## 使用说明

1. 访问 http://localhost:5000
2. 输入M3U文件链接或上传本地M3U文件
3. 使用界面功能进行编辑和管理

## 许可证

MIT 