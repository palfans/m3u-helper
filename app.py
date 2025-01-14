import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import subprocess
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'instance/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def parse_m3u(content):
    """解析M3U文件内容"""
    lines = content.split('\n')
    entries = []
    current_entry = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            # 解析EXTINF行
            info = line[8:].split(',', 1)
            duration = info[0]
            title = info[1] if len(info) > 1 else ''
            current_entry = {
                'duration': duration,
                'title': title,
                'url': ''
            }
        elif not line.startswith('#') and current_entry is not None:
            current_entry['url'] = line
            entries.append(current_entry)
            current_entry = None
            
    return entries

def get_video_info(url):
    """使用ffmpeg获取视频信息"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', url],
            capture_output=True,
            text=True
        )
        return json.loads(result.stdout)
    except Exception as e:
        return {'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/parse', methods=['POST'])
def parse():
    if 'url' in request.form:
        # TODO: 实现URL解析
        return jsonify({'error': 'URL parsing not implemented yet'})
    elif 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'})
            
        if file:
            content = file.read().decode('utf-8')
            entries = parse_m3u(content)
            return jsonify({'entries': entries})
            
    return jsonify({'error': 'Invalid request'})

@app.route('/video-info', methods=['POST'])
def video_info():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'})
        
    info = get_video_info(url)
    return jsonify(info)

if __name__ == '__main__':
    app.run(debug=True) 