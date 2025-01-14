document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('m3uForm');
    const playlist = document.getElementById('playlist');
    const downloadBtn = document.getElementById('downloadBtn');
    const checkAllBtn = document.getElementById('checkAllBtn');
    const videoInfoModal = new bootstrap.Modal(document.getElementById('videoInfoModal'));
    
    let currentEntries = [];
    let checkingInProgress = false;
    
    // 初始化拖拽排序
    const sortable = new Sortable(playlist, {
        animation: 150,
        ghostClass: 'bg-light',
        onEnd: function() {
            // 更新条目顺序
            updateEntries();
        }
    });

    // 处理表单提交
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = new FormData();
        const urlInput = document.getElementById('m3uUrl');
        const fileInput = document.getElementById('m3uFile');
        
        if (urlInput.value) {
            formData.append('url', urlInput.value);
        } else if (fileInput.files.length > 0) {
            formData.append('file', fileInput.files[0]);
        } else {
            alert('请输入URL或选择文件');
            return;
        }
        
        try {
            const response = await fetch('/parse', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            if (data.error) {
                alert(data.error);
                return;
            }
            
            currentEntries = data.entries;
            renderPlaylist(currentEntries);
            downloadBtn.style.display = 'block';
            checkAllBtn.style.display = 'block';
        } catch (error) {
            console.error('Error:', error);
            alert('解析失败');
        }
    });

    // 处理下载按钮点击
    downloadBtn.addEventListener('click', async function() {
        if (!currentEntries.length) {
            alert('没有可下载的内容');
            return;
        }
        
        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ entries: currentEntries })
            });
            
            if (response.ok) {
                // 创建一个临时链接来下载文件
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'playlist.m3u';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();
            } else {
                const error = await response.json();
                alert(error.error || '下载失败');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('下载失败');
        }
    });

    // 处理批量检查按钮点击
    checkAllBtn.addEventListener('click', async function() {
        if (!currentEntries.length) {
            alert('没有需要检查的视频');
            return;
        }

        if (checkingInProgress) {
            alert('检查正在进行中，请等待完成');
            return;
        }

        checkingInProgress = true;
        checkAllBtn.disabled = true;
        checkAllBtn.innerHTML = '<div class="loading-spinner"></div> 检查中...';
        
        try {
            const items = playlist.children;
            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                const url = item.querySelector('.info-btn').dataset.url;
                const title = item.querySelector('strong').textContent;
                
                // 添加检查状态标签
                const statusSpan = document.createElement('span');
                statusSpan.className = 'check-status checking';
                statusSpan.textContent = '检查中';
                item.querySelector('.info-btn').insertAdjacentElement('afterend', statusSpan);
                
                // 添加检查信息区域
                let checkInfo = item.querySelector('.check-info');
                if (!checkInfo) {
                    checkInfo = document.createElement('div');
                    checkInfo.className = 'check-info checking';
                    checkInfo.innerHTML = '<div class="loading-spinner"></div> 正在检查视频信息...';
                    item.appendChild(checkInfo);
                }
                
                try {
                    const response = await fetch('/video-info', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ url })
                    });
                    
                    const data = await response.json();
                    const isSuccess = !('error' in data);
                    
                    // 更新状态标签
                    statusSpan.className = `check-status ${isSuccess ? 'success' : 'error'}`;
                    statusSpan.textContent = isSuccess ? '正常' : '错误';
                    
                    // 更新检查信息
                    checkInfo.className = `check-info ${isSuccess ? 'success' : 'error'}`;
                    if (isSuccess) {
                        checkInfo.innerHTML = `
                            <div><strong>格式:</strong> ${data.format?.format_name || '未知'}</div>
                            <div><strong>时长:</strong> ${data.format?.duration || '未知'}秒</div>
                            <div><strong>大小:</strong> ${data.format?.size || '未知'}字节</div>
                            <div><strong>比特率:</strong> ${data.format?.bit_rate || '未知'}bps</div>
                            ${data.streams?.find(s => s.codec_type === 'video') ? `
                                <div><strong>视频编码:</strong> ${data.streams.find(s => s.codec_type === 'video').codec_name || '未知'}</div>
                                <div><strong>分辨率:</strong> ${data.streams.find(s => s.codec_type === 'video').width || '?'}x${data.streams.find(s => s.codec_type === 'video').height || '?'}</div>
                            ` : ''}
                        `;
                    } else {
                        checkInfo.innerHTML = `<div class="text-danger">${data.error}</div>`;
                    }
                } catch (error) {
                    console.error('Error:', error);
                    statusSpan.className = 'check-status error';
                    statusSpan.textContent = '错误';
                    checkInfo.className = 'check-info error';
                    checkInfo.innerHTML = '<div class="text-danger">检查失败</div>';
                }
            }
        } catch (error) {
            console.error('Error:', error);
            alert('检查过程中发生错误');
        } finally {
            checkingInProgress = false;
            checkAllBtn.disabled = false;
            checkAllBtn.textContent = '检查所有视频';
        }
    });

    // 更新条目顺序
    function updateEntries() {
        const items = playlist.children;
        const newEntries = [];
        
        for (let item of items) {
            const title = item.querySelector('strong').textContent;
            const duration = item.querySelector('.video-info').textContent.match(/时长: (.*?)秒/)[1];
            const url = item.querySelector('.info-btn').dataset.url;
            
            newEntries.push({
                title: title === '未命名' ? '' : title,
                duration: duration,
                url: url
            });
        }
        
        currentEntries = newEntries;
    }

    // 渲染播放列表
    function renderPlaylist(entries) {
        playlist.innerHTML = '';
        entries.forEach((entry, index) => {
            const item = document.createElement('div');
            item.className = 'playlist-item';
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${entry.title || '未命名'}</strong>
                        <div class="video-info">
                            时长: ${entry.duration}秒
                            <br>
                            URL: ${entry.url}
                        </div>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-info me-2 info-btn" data-url="${entry.url}">
                            信息
                        </button>
                        <button class="btn btn-sm btn-danger delete-btn">
                            删除
                        </button>
                    </div>
                </div>
            `;
            
            // 绑定删除按钮事件
            item.querySelector('.delete-btn').addEventListener('click', function() {
                item.remove();
                updateEntries();
                if (playlist.children.length === 0) {
                    downloadBtn.style.display = 'none';
                    checkAllBtn.style.display = 'none';
                }
            });
            
            // 绑定信息按钮事件
            item.querySelector('.info-btn').addEventListener('click', async function() {
                const url = this.dataset.url;
                try {
                    const response = await fetch('/video-info', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ url })
                    });
                    
                    const data = await response.json();
                    document.getElementById('videoInfoContent').textContent = 
                        JSON.stringify(data, null, 2);
                    videoInfoModal.show();
                } catch (error) {
                    console.error('Error:', error);
                    alert('获取视频信息失败');
                }
            });
            
            playlist.appendChild(item);
        });
    }
}); 