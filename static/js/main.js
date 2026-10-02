document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('m3uForm');
    const playlist = document.getElementById('playlist');
    const downloadBtn = document.getElementById('downloadBtn');
    const checkAllBtn = document.getElementById('checkAllBtn');
    const reportBtn = document.getElementById('reportBtn');
    const videoInfoModal = new bootstrap.Modal(document.getElementById('videoInfoModal'));
    
    let currentEntries = [];
    let currentSourceUrl = '';
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

    function setButtonVisibility() {
        const hasEntries = currentEntries.length > 0;
        downloadBtn.style.display = hasEntries ? 'block' : 'none';
        checkAllBtn.style.display = hasEntries ? 'block' : 'none';
        reportBtn.style.display = currentSourceUrl ? 'block' : 'none';
    }

    function addTextLine(parent, label, value) {
        const line = document.createElement('div');
        line.textContent = `${label}: ${value || '未知'}`;
        parent.appendChild(line);
    }

    function setCheckingState(item) {
        let status = item.querySelector('.check-status');
        if (!status) {
            status = document.createElement('span');
            item.querySelector('.info-btn').insertAdjacentElement('afterend', status);
        }
        status.className = 'check-status checking';
        status.textContent = '检查中';

        let info = item.querySelector('.check-info');
        if (!info) {
            info = document.createElement('div');
            item.appendChild(info);
        }
        info.className = 'check-info checking';
        info.textContent = '正在检查视频信息...';
    }

    function showResult(item, result) {
        const success = result.status === 'ok';
        const details = result.details || {};
        const status = item.querySelector('.check-status');
        const info = item.querySelector('.check-info');
        status.className = `check-status ${success ? 'success' : 'error'}`;
        status.textContent = success ? '正常' : '错误';
        info.className = `check-info ${success ? 'success' : 'error'}`;
        info.textContent = '';
        if (!success) {
            info.textContent = details.error || result.error || '检查失败';
            return;
        }
        addTextLine(info, '探测方式', details.method);
        addTextLine(info, '格式', details.format);
        (details.video || []).forEach((stream, index) => {
            addTextLine(info, `视频${index + 1}`, `${stream.codec || '未知'}，${stream.resolution || '未知分辨率'}`);
        });
        (details.audio || []).forEach((stream, index) => {
            addTextLine(info, `音频${index + 1}`, `${stream.codec || '未知'}，${stream.sample_rate || '未知采样率'}，${stream.channels || '未知声道'}`);
        });
    }

    async function readJsonResponse(response) {
        const data = await response.json();
        if (!response.ok || data.error) {
            throw new Error(data.error || '请求失败');
        }
        return data;
    }

    // 处理表单提交
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = new FormData();
        const urlInput = document.getElementById('m3uUrl');
        const fileInput = document.getElementById('m3uFile');
        currentSourceUrl = urlInput.value.trim();
        if (currentSourceUrl) {
            formData.append('url', currentSourceUrl);
        } else if (fileInput.files.length > 0) {
            currentSourceUrl = '';
            formData.append('file', fileInput.files[0]);
        } else {
            alert('请输入 URL 或选择文件');
            return;
        }
        
        try {
            const response = await fetch('/parse', {
                method: 'POST',
                body: formData
            });
            
            const data = await readJsonResponse(response);
            currentEntries = data.entries;
            renderPlaylist(currentEntries);
            setButtonVisibility();
        } catch (error) {
            alert(error.message || '解析失败');
        }
    });

    reportBtn.addEventListener('click', async function() {
        if (!currentSourceUrl) {
            alert('HTML 报告需要使用 M3U8 URL');
            return;
        }
        reportBtn.disabled = true;
        try {
            const response = await fetch('/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: currentSourceUrl })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || '报告生成失败');
            }
            const blobUrl = window.URL.createObjectURL(await response.blob());
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = 'm3u8-report.html';
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(blobUrl);
        } catch (error) {
            alert(error.message || '报告生成失败');
        } finally {
            reportBtn.disabled = false;
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
        if (!currentEntries.length || checkingInProgress) {
            return;
        }
        checkingInProgress = true;
        checkAllBtn.disabled = true;
        checkAllBtn.textContent = '检查中...';
        const items = Array.from(playlist.children);
        items.forEach(setCheckingState);
        try {
            const data = await readJsonResponse(await fetch('/check-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries: currentEntries })
            }));
            data.results.forEach((result, index) => showResult(items[index], result));
        } catch (error) {
            items.forEach(item => {
                const status = item.querySelector('.check-status');
                const info = item.querySelector('.check-info');
                status.className = 'check-status error';
                status.textContent = '错误';
                info.className = 'check-info error';
                info.textContent = error.message || '检查失败';
            });
        } finally {
            checkingInProgress = false;
            checkAllBtn.disabled = false;
            checkAllBtn.textContent = '检查所有视频';
        }
    });

    // 更新条目顺序
    function updateEntries() {
        currentEntries = Array.from(playlist.children).map(item => ({
            title: item.querySelector('strong').textContent,
            duration: item.dataset.duration || '-1',
            url: item.dataset.url
        }));
        setButtonVisibility();
    }

    // 渲染播放列表
    function renderPlaylist(entries) {
        playlist.textContent = '';
        entries.forEach(entry => {
            const item = document.createElement('div');
            item.className = 'playlist-item';
            item.dataset.duration = entry.duration || '-1';
            item.dataset.url = entry.url;

            const header = document.createElement('div');
            header.className = 'd-flex justify-content-between align-items-center';
            const text = document.createElement('div');
            const title = document.createElement('strong');
            title.textContent = entry.title || '未命名';
            const metadata = document.createElement('div');
            metadata.className = 'video-info';
            metadata.textContent = `时长: ${entry.duration || '-1'}秒`;
            const urlText = document.createElement('div');
            urlText.textContent = `URL: ${entry.url}`;
            metadata.appendChild(document.createElement('br'));
            metadata.appendChild(urlText);
            text.appendChild(title);
            text.appendChild(metadata);

            const actions = document.createElement('div');
            const infoButton = document.createElement('button');
            infoButton.className = 'btn btn-sm btn-info me-2 info-btn';
            infoButton.textContent = '信息';
            infoButton.dataset.url = entry.url;
            const deleteButton = document.createElement('button');
            deleteButton.className = 'btn btn-sm btn-danger delete-btn';
            deleteButton.textContent = '删除';
            actions.appendChild(infoButton);
            actions.appendChild(deleteButton);
            header.appendChild(text);
            header.appendChild(actions);
            item.appendChild(header);

            // 绑定删除按钮事件
            deleteButton.addEventListener('click', function() {
                item.remove();
                updateEntries();
            });

            // 绑定信息按钮事件
            infoButton.addEventListener('click', async function() {
                try {
                    const response = await fetch('/video-info', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ url: entry.url })
                    });
                    const data = await readJsonResponse(response);
                    document.getElementById('videoInfoContent').textContent = 
                        JSON.stringify(data, null, 2);
                    videoInfoModal.show();
                } catch (error) {
                    alert(error.message || '获取视频信息失败');
                }
            });

            playlist.appendChild(item);
        });
    }
});
