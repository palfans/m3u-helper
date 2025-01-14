document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('m3uForm');
    const playlist = document.getElementById('playlist');
    const videoInfoModal = new bootstrap.Modal(document.getElementById('videoInfoModal'));
    
    // 初始化拖拽排序
    new Sortable(playlist, {
        animation: 150,
        ghostClass: 'bg-light'
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
            
            renderPlaylist(data.entries);
        } catch (error) {
            console.error('Error:', error);
            alert('解析失败');
        }
    });

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