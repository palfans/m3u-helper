import os
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import subprocess
import json
import requests
from urllib.parse import urlparse
import tempfile
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'instance/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def is_valid_url(url):
    """验证URL是否有效"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def download_m3u_content(url):
    """从URL下载M3U文件内容"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        raise Exception(f"下载M3U文件失败: {str(e)}")

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

def generate_m3u(entries):
    """生成M3U文件内容"""
    content = ['#EXTM3U']
    for entry in entries:
        content.append(f'#EXTINF:{entry["duration"]},{entry["title"]}')
        content.append(entry['url'])
    return '\n'.join(content)

def get_video_info(url):
    """使用ffmpeg获取视频信息"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', url],
            capture_output=True,
            text=True,
            timeout=10  # 添加超时限制
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {'error': '无法读取视频信息'}
    except subprocess.TimeoutExpired:
        return {'error': '获取视频信息超时'}
    except Exception as e:
        return {'error': str(e)}

def check_video_status(entry):
    """检查单个视频的状态"""
    url = entry['url']
    info = get_video_info(url)
    
    if 'error' in info:
        status = 'error'
        details = info['error']
    else:
        status = 'ok'
        # 提取关键信息
        details = {
            'format': info.get('format', {}).get('format_name', '未知'),
            'duration': info.get('format', {}).get('duration', '未知'),
            'size': info.get('format', {}).get('size', '未知'),
            'bit_rate': info.get('format', {}).get('bit_rate', '未知')
        }
        if 'streams' in info:
            for stream in info['streams']:
                if stream.get('codec_type') == 'video':
                    details.update({
                        'video_codec': stream.get('codec_name', '未知'),
                        'resolution': f"{stream.get('width', '?')}x{stream.get('height', '?')}"
                    })
                    break
    
    return {
        'title': entry['title'],
        'url': url,
        'status': status,
        'details': details
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/parse', methods=['POST'])
def parse():
    if 'url' in request.form:
        url = request.form['url']
        if not is_valid_url(url):
            return jsonify({'error': '无效的URL格式'})
        
        try:
            content = download_m3u_content(url)
            entries = parse_m3u(content)
            return jsonify({'entries': entries})
        except Exception as e:
            return jsonify({'error': str(e)})
            
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

@app.route('/check-all', methods=['POST'])
def check_all():
    """批量检查所有视频的状态"""
    entries = request.json.get('entries', [])
    if not entries:
        return jsonify({'error': '没有需要检查的视频'})
    
    try:
        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(check_video_status, entries))
        
        return jsonify({
            'total': len(results),
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/download', methods=['POST'])
def download():
    """下载生成的M3U文件"""
    try:
        entries = request.json.get('entries', [])
        if not entries:
            return jsonify({'error': '没有可下载的内容'})
            
        content = generate_m3u(entries)
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.m3u', delete=False) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
            
        return send_file(
            temp_path,
            as_attachment=True,
            download_name='playlist.m3u',
            mimetype='application/x-mpegurl'
        )
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        # 清理临时文件
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass

if __name__ == '__main__':
    app.run(debug=True) 