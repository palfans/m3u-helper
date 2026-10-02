import os
from flask import Flask, Response, jsonify, render_template, request, send_file
import tempfile
from concurrent.futures import ThreadPoolExecutor

from probe import parse_m3u as parse_playlist
from probe import ProbeError, fetch_m3u_content, probe_url, render_html_report, validate_url

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'instance/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
app.config['ALLOW_PRIVATE_URLS'] = os.environ.get('M3U_HELPER_ALLOW_PRIVATE_URLS') == '1'
app.config['PROBE_TIMEOUT'] = int(os.environ.get('M3U_HELPER_PROBE_TIMEOUT', '10'))
app.config['CHECK_WORKERS'] = int(os.environ.get('M3U_HELPER_CHECK_WORKERS', '1'))
if app.config['CHECK_WORKERS'] < 1:
    raise ValueError('M3U_HELPER_CHECK_WORKERS 必须大于或等于 1')

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def is_valid_url(url):
    try:
        validate_url(url, allow_private=app.config['ALLOW_PRIVATE_URLS'])
    except ValueError:
        return False
    return True

def download_m3u_content(url):
    return fetch_m3u_content(
        url,
        timeout=app.config['PROBE_TIMEOUT'],
        allow_private=app.config['ALLOW_PRIVATE_URLS'],
    )


def parse_m3u(content, base_url=None):
    return parse_playlist(content, base_url)

def generate_m3u(entries):
    """生成M3U文件内容"""
    content = ['#EXTM3U']
    for entry in entries:
        content.append(f'#EXTINF:{entry["duration"]},{entry["title"]}')
        content.append(entry['url'])
    return '\n'.join(content)

def get_video_info(url):
    return probe_url(
        url,
        timeout=app.config['PROBE_TIMEOUT'],
        allow_private=app.config['ALLOW_PRIVATE_URLS'],
    )

def check_video_status(entry):
    if not isinstance(entry, dict):
        return {
            'title': '',
            'url': '',
            'status': 'error',
            'details': {'error': '列表项必须是 JSON 对象'},
        }
    url = entry.get('url', '')
    try:
        info = get_video_info(url)
    except ValueError as exc:
        info = {'available': False, 'method': 'validation', 'error': str(exc)}
    status = 'ok' if info.get('available') else 'error'
    format_info = info.get('format') or {}
    details = {
        'method': info.get('method', '未知'),
        'format': format_info.get('format_name', '未知'),
        'duration': format_info.get('duration', '未知'),
        'size': format_info.get('size', '未知'),
        'bit_rate': format_info.get('bit_rate', '未知'),
        'video': info.get('video', []),
        'audio': info.get('audio', []),
    }
    if not info.get('available'):
        details['error'] = info.get('error', '无法读取视频信息')
    return {
        'title': entry.get('title', ''),
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
            return jsonify({'error': '无效的URL格式'}), 400
        
        try:
            content, final_url = download_m3u_content(url)
            entries = parse_m3u(content, final_url)
            return jsonify({'entries': entries})
        except (ProbeError, UnicodeError, ValueError) as e:
            return jsonify({'error': str(e)}), 400
            
    elif 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        try:
            content = file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return jsonify({'error': '上传文件编码必须为 UTF-8'}), 400
        try:
            entries = parse_m3u(content)
        except (UnicodeError, ValueError) as e:
            return jsonify({'error': str(e)}), 400
        return jsonify({'entries': entries})
            
    return jsonify({'error': 'Invalid request'}), 400

@app.route('/video-info', methods=['POST'])
def video_info():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': '请求体必须是 JSON 对象'}), 400
    url = payload.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
        
    if not is_valid_url(url):
        return jsonify({'error': '只支持 HTTP 或 HTTPS URL'}), 400
    return jsonify(get_video_info(url))


@app.route('/report', methods=['POST'])
def report():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': '请求体必须是 JSON 对象'}), 400
    url = payload.get('url')
    if not is_valid_url(url):
        return jsonify({'error': '只支持 HTTP 或 HTTPS URL'}), 400
    result = get_video_info(url)
    response = Response(render_html_report(result), mimetype='text/html')
    response.headers['Content-Disposition'] = 'inline; filename="m3u8-report.html"'
    return response

@app.route('/check-all', methods=['POST'])
def check_all():
    """批量检查所有视频的状态"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': '请求体必须是 JSON 对象'}), 400
    entries = payload.get('entries', [])
    if not isinstance(entries, list) or not entries:
        return jsonify({'error': '没有需要检查的视频'}), 400
    
    try:
        if app.config['CHECK_WORKERS'] == 1:
            results = [check_video_status(entry) for entry in entries]
        else:
            with ThreadPoolExecutor(max_workers=app.config['CHECK_WORKERS']) as executor:
                results = list(executor.map(check_video_status, entries))
        return jsonify({
            'total': len(results),
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    """下载生成的M3U文件"""
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'error': '请求体必须是 JSON 对象'}), 400
        entries = payload.get('entries', [])
        if not isinstance(entries, list) or not entries:
            return jsonify({'error': '没有可下载的内容'}), 400
            
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
        return jsonify({'error': str(e)}), 500
    finally:
        # 清理临时文件
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except OSError:
                pass

if __name__ == '__main__':
    app.run(debug=True)
