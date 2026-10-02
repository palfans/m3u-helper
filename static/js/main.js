document.addEventListener('DOMContentLoaded', () => {
    const get = (id) => document.getElementById(id);
    const dom = {
        form: get('m3uForm'),
        urlInput: get('m3uUrl'),
        fileInput: get('m3uFile'),
        fileName: get('fileName'),
        parseButton: get('parseBtn'),
        connectionStatus: get('connectionStatus'),
        sourceState: get('sourceState'),
        sourceMeta: get('sourceMeta'),
        dashboard: get('dashboard'),
        playlist: get('playlist'),
        playlistSearch: get('playlistSearch'),
        statusFilter: get('statusFilter'),
        groupFilter: get('groupFilter'),
        selectedCount: get('selectedCount'),
        checkSelectedButton: get('checkSelectedBtn'),
        visibleCount: get('visibleCount'),
        emptyState: get('emptyState'),
        filterEmpty: get('filterEmpty'),
        progressPanel: get('progressPanel'),
        progressTitle: get('progressTitle'),
        progressLabel: get('progressLabel'),
        progressBar: get('progressBar'),
        currentChecking: get('currentChecking'),
        summaryTotal: get('summaryTotal'),
        summaryAvailable: get('summaryAvailable'),
        summaryErrors: get('summaryErrors'),
        summaryPending: get('summaryPending'),
        checkWorkers: get('checkWorkers'),
        checkAllButton: get('checkAllBtn'),
        stopCheckButton: get('stopCheckBtn'),
        reportButton: get('reportBtn'),
        downloadButton: get('downloadBtn'),
        videoInfoModal: get('videoInfoModal'),
        videoInfoTitle: get('videoInfoTitle'),
        videoInfoContent: get('videoInfoContent'),
        closeModalButton: get('closeModalButton'),
        toastContainer: get('toastContainer'),
    };

    const state = {
        entries: [],
        results: [],
        groupFilter: 'all',
        selected: new Set(),
        checkScope: null,
        sourceUrl: '',
        checking: false,
        stopRequested: false,
        requestToken: 0,
        parseController: null,
        checkController: null,
        infoController: null,
        reportController: null,
        downloadController: null,
        objectUrls: new Set(),
    };

    const statusLabels = {
        pending: '待检查',
        checking: '检查中',
        ok: '可用',
        error: '不可用',
    };

    if (window.Sortable) {
        new window.Sortable(dom.playlist, {
            animation: 180,
            handle: '.drag-handle',
            ghostClass: 'sortable-ghost',
            onEnd: syncCurrentOrder,
        });
    }

    function text(value, fallback = '未知') {
        if (value === null || value === undefined || value === '') {
            return fallback;
        }
        return String(value);
    }

    function formatDuration(value) {
        const seconds = Number.parseFloat(value);
        if (!Number.isFinite(seconds) || seconds < 0) {
            return '时长未知';
        }
        if (seconds >= 3600) {
            return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分`;
        }
        if (seconds >= 60) {
            return `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}秒`;
        }
        return `${Math.round(seconds)}秒`;
    }

    function formatNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number.toLocaleString('zh-CN') : text(value);
    }

    function setConnection(message, kind = '') {
        const label = dom.connectionStatus.querySelector('span:last-child');
        label.textContent = message;
        dom.connectionStatus.className = 'topbar-status';
        if (kind) {
            dom.connectionStatus.classList.add(`is-${kind}`);
        }
    }

    function setSourceState(message, kind = '') {
        dom.sourceState.textContent = message;
        dom.sourceState.className = 'source-state';
        if (kind) {
            dom.sourceState.classList.add(`is-${kind}`);
        }
    }

    function showToast(message, kind = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${kind === 'error' ? 'is-error' : kind === 'success' ? 'is-success' : ''}`;
        toast.textContent = text(message, '操作完成');
        dom.toastContainer.appendChild(toast);
        window.setTimeout(() => toast.remove(), 4200);
    }

    function clearDownloadUrls() {
        state.objectUrls.forEach((objectUrl) => window.URL.revokeObjectURL(objectUrl));
        state.objectUrls.clear();
    }

    function clearStaleState() {
        state.requestToken += 1;
        state.parseController?.abort();
        state.checkController?.abort();
        state.infoController?.abort();
        state.reportController?.abort();
        state.downloadController?.abort();
        state.parseController = null;
        state.checkController = null;
        state.infoController = null;
        state.reportController = null;
        state.downloadController = null;
        state.entries = [];
        state.results = [];
        state.selected.clear();
        state.checkScope = null;
        state.sourceUrl = '';
        state.checking = false;
        state.stopRequested = false;
        clearDownloadUrls();
        dom.playlist.replaceChildren();
        dom.dashboard.classList.add('is-hidden');
        dom.emptyState.classList.add('is-hidden');
        dom.filterEmpty.classList.add('is-hidden');
        dom.playlistSearch.value = '';
        dom.statusFilter.value = 'all';
        dom.groupFilter.replaceChildren(new Option('全部分组', 'all'));
        dom.groupFilter.value = 'all';
        state.groupFilter = 'all';
        dom.visibleCount.textContent = '显示 0 条';
        dom.toastContainer.replaceChildren();
        if (dom.videoInfoModal.open) {
            dom.videoInfoModal.close();
        }
        dom.videoInfoContent.replaceChildren();
        dom.sourceMeta.textContent = '尚未载入数据';
        setSourceState('等待导入');
        setConnection('准备就绪');
        updateSummary();
        updateProgress();
        updateActionState();
    }

    function setParsingState(isParsing) {
        dom.parseButton.disabled = isParsing;
        dom.parseButton.querySelector('span:first-child').textContent = isParsing ? '读取中…' : '解析列表';
        dom.urlInput.disabled = isParsing;
        dom.fileInput.disabled = isParsing;
    }

    function setCheckButtonLabel(label) {
        const pulse = document.createElement('span');
        pulse.className = 'button-pulse';
        pulse.setAttribute('aria-hidden', 'true');
        const labelNode = document.createElement('span');
        labelNode.textContent = label;
        dom.checkAllButton.replaceChildren(pulse, labelNode);
    }

    function getStatus(index) {
        return state.results[index]?.status || 'pending';
    }

    function entryGroups(entry) {
        const groups = Array.isArray(entry?.groups) ? entry.groups : [];
        return groups.map((group) => text(group, '')).filter(Boolean);
    }

    function getGroupIndexes() {
        const selected = state.groupFilter;
        return state.entries.reduce((indexes, entry, index) => {
            const groups = entryGroups(entry);
            if (selected === 'all' || (selected === '__ungrouped' && !groups.length) || groups.includes(selected)) {
                indexes.push(index);
            }
            return indexes;
        }, []);
    }

    function getScopeIndexes() {
        return state.checkScope || getGroupIndexes();
    }

    function updateGroupOptions() {
        const counts = new Map();
        let ungrouped = 0;
        state.entries.forEach((entry) => {
            const groups = entryGroups(entry);
            if (!groups.length) {
                ungrouped += 1;
            }
            groups.forEach((group) => counts.set(group, (counts.get(group) || 0) + 1));
        });
        const options = [new Option(`全部分组 · ${state.entries.length}`, 'all')];
        Array.from(counts.entries()).sort(([left], [right]) => left.localeCompare(right, 'zh-CN')).forEach(([group, count]) => {
            options.push(new Option(`${group} · ${count}`, group));
        });
        if (ungrouped) {
            options.push(new Option(`未分组 · ${ungrouped}`, '__ungrouped'));
        }
        dom.groupFilter.replaceChildren(...options);
        dom.groupFilter.value = options.some((option) => option.value === state.groupFilter) ? state.groupFilter : 'all';
        state.groupFilter = dom.groupFilter.value;
    }

    function updateSummary() {
        const indexes = getScopeIndexes();
        const total = indexes.length;
        const available = indexes.filter((index) => state.results[index]?.status === 'ok').length;
        const errors = indexes.filter((index) => state.results[index]?.status === 'error').length;
        const pending = Math.max(0, total - available - errors);
        dom.summaryTotal.textContent = String(total);
        dom.summaryAvailable.textContent = String(available);
        dom.summaryErrors.textContent = String(errors);
        dom.summaryPending.textContent = String(pending);
    }

    function updateProgress() {
        const indexes = getScopeIndexes();
        const total = indexes.length;
        const checked = indexes.filter((index) => state.results[index]).length;
        const percent = total ? Math.round((checked / total) * 100) : 0;
        const workers = Number(dom.checkWorkers.value);
        dom.progressLabel.textContent = `${checked} / ${total}`;
        dom.progressBar.style.width = `${percent}%`;
        dom.progressPanel.classList.toggle('is-running', state.checking);
        if (state.checking) {
            const mode = workers === 1 ? '顺序检查' : `${workers} 路并发检查`;
            dom.progressTitle.textContent = `正在${mode}`;
            dom.currentChecking.textContent = `${mode} · ${total} 条`;
        } else if (total && checked === total) {
            dom.progressTitle.textContent = '检查完成';
            dom.currentChecking.textContent = '全部完成';
        } else if (checked) {
            dom.progressTitle.textContent = '检查未完成';
            dom.currentChecking.textContent = `已完成 ${checked} 条`;
        } else {
            dom.progressTitle.textContent = '准备检查';
            dom.currentChecking.textContent = '点击检查全部开始';
        }
    }

    function updateSelectionControls() {
        const selected = state.selected.size;
        dom.selectedCount.textContent = `已选 ${selected}`;
        dom.checkSelectedButton.disabled = selected === 0 || state.checking;
        dom.checkSelectedButton.title = selected ? `检查已选的 ${selected} 条视频` : '请选择视频后检查';
        Array.from(dom.playlist.children).forEach((card) => {
            const checkbox = card.querySelector('.entry-select');
            if (checkbox) {
                checkbox.checked = state.selected.has(Number(card.dataset.index));
                checkbox.disabled = state.checking;
            }
        });
    }

    function updateActionState() {
        const hasEntries = state.entries.length > 0;
        dom.dashboard.classList.toggle('is-hidden', !hasEntries);
        dom.checkAllButton.disabled = !hasEntries || state.checking;
        dom.stopCheckButton.classList.toggle('is-hidden', !state.checking);
        dom.stopCheckButton.disabled = !state.checking || state.stopRequested;
        dom.stopCheckButton.textContent = state.stopRequested ? '正在停止…' : '停止检查';
        dom.checkWorkers.disabled = !hasEntries || state.checking;
        dom.groupFilter.disabled = !hasEntries || state.checking;
        dom.checkSelectedButton.disabled = state.selected.size === 0 || state.checking;
        dom.reportButton.classList.toggle('is-hidden', !hasEntries);
        dom.reportButton.disabled = !state.sourceUrl || state.checking;
        dom.reportButton.title = state.sourceUrl ? '下载当前地址的 HTML 探测报告' : '上传文件后无法生成远程地址报告';
        dom.downloadButton.disabled = !hasEntries || state.checking;
        dom.checkAllButton.title = state.groupFilter === 'all' ? '按所选并发数检查所有条目' : '按所选并发数检查当前分组';
        if (state.checking) {
            setCheckButtonLabel('检查中…');
        } else if (state.groupFilter === 'all') {
            setCheckButtonLabel('检查全部');
        } else {
            setCheckButtonLabel('检查本组');
        }
        updateSelectionControls();
    }

    function addChip(container, value) {
        if (!value || value === '未知') {
            return;
        }
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.textContent = value;
        container.appendChild(chip);
    }

    function addResultValue(container, label, value) {
        const item = document.createElement('div');
        item.className = 'result-value';
        const labelNode = document.createElement('span');
        labelNode.textContent = label;
        const valueNode = document.createElement('strong');
        valueNode.textContent = text(value);
        item.append(labelNode, valueNode);
        container.appendChild(item);
    }

    function appendStreamRows(container, label, streams, type) {
        if (!streams?.length) {
            return;
        }
        const list = document.createElement('div');
        list.className = 'stream-list';
        streams.forEach((stream, index) => {
            const row = document.createElement('div');
            row.className = 'stream-row';
            const rowLabel = document.createElement('span');
            rowLabel.className = 'stream-label';
            rowLabel.textContent = `${label}${index + 1}`;
            const value = document.createElement('span');
            value.className = 'stream-value';
            if (type === 'video') {
                value.textContent = [
                    text(stream.codec),
                    text(stream.resolution, '未知分辨率'),
                    stream.frame_rate ? `${stream.frame_rate} fps` : '',
                ].filter(Boolean).join(' · ');
            } else {
                value.textContent = [
                    text(stream.codec),
                    stream.sample_rate ? `${stream.sample_rate} Hz` : '',
                    stream.channels ? `${stream.channels} 声道` : '',
                    stream.channel_layout || stream.language || '',
                ].filter(Boolean).join(' · ');
            }
            row.append(rowLabel, value);
            list.appendChild(row);
        });
        container.appendChild(list);
    }

    function renderCardResult(card, result, status) {
        card.dataset.status = status;
        const badge = card.querySelector('.status-badge');
        badge.className = `status-badge status-${status}`;
        badge.textContent = statusLabels[status] || status;
        const resultPanel = card.querySelector('.result-panel');
        resultPanel.replaceChildren();
        resultPanel.className = 'result-panel';
        if (status === 'checking') {
            resultPanel.classList.add('result-checking');
            const message = document.createElement('p');
            message.className = 'result-hint';
            message.textContent = '正在等待服务端返回探测结果…';
            resultPanel.appendChild(message);
            return;
        }
        if (!result) {
            const message = document.createElement('p');
            message.className = 'result-hint';
            message.textContent = '等待检查';
            resultPanel.appendChild(message);
            return;
        }
        const details = result.details || result;
        if (status === 'error') {
            resultPanel.classList.add('result-error');
            const message = document.createElement('p');
            message.className = 'error-copy';
            const errorText = text(details.error || result.error, '检查失败');
            message.textContent = errorText.length > 280 ? `${errorText.slice(0, 280)}…` : errorText;
            message.title = errorText;
            resultPanel.appendChild(message);
            return;
        }
        resultPanel.classList.add('result-ok');
        const summary = document.createElement('div');
        summary.className = 'result-grid';
        addResultValue(summary, '探测方式', details.method);
        addResultValue(summary, '格式', details.format);
        addResultValue(summary, '时长', details.duration);
        addResultValue(summary, '码率', details.bit_rate);
        resultPanel.appendChild(summary);
        appendStreamRows(resultPanel, '视频', details.video, 'video');
        appendStreamRows(resultPanel, '音频', details.audio, 'audio');
    }

    function makeButton(label, className, title) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = className;
        button.textContent = label;
        if (title) {
            button.title = title;
        }
        return button;
    }

    function createPlaylistCard(entry, index) {
        const card = document.createElement('article');
        card.className = 'playlist-item';
        card.dataset.index = String(index);

        const handle = document.createElement('span');
        handle.className = 'drag-handle';
        handle.textContent = '⋮⋮';
        handle.title = '拖动调整顺序';
        handle.setAttribute('aria-label', '拖动调整顺序');

        const main = document.createElement('div');
        main.className = 'item-main';
        const header = document.createElement('div');
        header.className = 'item-head';

        const titleGroup = document.createElement('div');
        titleGroup.className = 'item-title-group';
        const selectionLabel = document.createElement('label');
        selectionLabel.className = 'selection-control';
        selectionLabel.title = '选择此视频';
        const selection = document.createElement('input');
        selection.type = 'checkbox';
        selection.className = 'entry-select';
        selection.checked = state.selected.has(index);
        selection.setAttribute('aria-label', `选择 ${text(entry.title, '视频')}`);
        selection.addEventListener('change', () => {
            if (selection.checked) {
                state.selected.add(index);
            } else {
                state.selected.delete(index);
            }
            state.checkScope = null;
            updateSummary();
            updateProgress();
            updateActionState();
        });
        selectionLabel.appendChild(selection);
        const number = document.createElement('span');
        number.className = 'item-number';
        number.textContent = String(index + 1).padStart(2, '0');
        const titleBlock = document.createElement('div');
        const title = document.createElement('h3');
        title.textContent = text(entry.title, '未命名');
        const urlRow = document.createElement('div');
        urlRow.className = 'item-url-row';
        const url = document.createElement('span');
        url.className = 'item-url';
        url.textContent = text(entry.url, '地址未知');
        const copyButton = makeButton('复制', 'small-button copy-button', '复制播放地址');
        copyButton.addEventListener('click', () => copyUrl(entry.url));
        urlRow.append(url, copyButton);
        titleBlock.append(title, urlRow);
        titleGroup.append(selectionLabel, number, titleBlock);

        const actions = document.createElement('div');
        actions.className = 'item-actions';
        const badge = document.createElement('span');
        badge.className = 'status-badge status-pending';
        badge.textContent = statusLabels.pending;
        badge.setAttribute('aria-live', 'polite');
        const infoButton = makeButton('详情', 'small-button', '查看视频和音频信息');
        infoButton.addEventListener('click', () => openDetails(index));
        const deleteButton = makeButton('删除', 'small-button danger', '从当前列表移除');
        deleteButton.addEventListener('click', () => removeEntry(index));
        actions.append(badge, infoButton, deleteButton);
        header.append(titleGroup, actions);

        const chips = document.createElement('div');
        chips.className = 'item-chips';
        addChip(chips, entry.resolution);
        addChip(chips, entry.codecs);
        addChip(chips, entry.bandwidth ? `${formatNumber(entry.bandwidth)} bps` : '');
        entryGroups(entry).forEach((group) => addChip(chips, group));
        addChip(chips, formatDuration(entry.duration));

        const resultPanel = document.createElement('div');
        resultPanel.className = 'result-panel';
        main.append(header, chips, resultPanel);
        card.append(handle, main);
        renderCardResult(card, null, 'pending');
        return card;
    }

    function renderPlaylist() {
        dom.playlist.replaceChildren();
        state.entries.forEach((entry, index) => {
            const card = createPlaylistCard(entry, index);
            renderCardResult(card, state.results[index], getStatus(index));
            dom.playlist.appendChild(card);
        });
        dom.emptyState.classList.toggle('is-hidden', state.entries.length > 0);
        updateCards();
        applyFilters();
    }

    function updateCards() {
        Array.from(dom.playlist.children).forEach((card, index) => {
            renderCardResult(card, state.results[index], getStatus(index));
            const disabled = state.checking;
            card.querySelectorAll('.small-button').forEach((button) => {
                button.disabled = disabled;
            });
        });
        updateSummary();
        updateProgress();
        updateActionState();
    }

    function applyFilters() {
        const query = dom.playlistSearch.value.trim().toLowerCase();
        const statusFilter = dom.statusFilter.value;
        let visible = 0;
        Array.from(dom.playlist.children).forEach((card, index) => {
            const entry = state.entries[index];
            const status = getStatus(index);
            const searchable = `${text(entry?.title, '')} ${text(entry?.url, '')}`.toLowerCase();
            const groups = entryGroups(entry);
            const groupMatched = state.groupFilter === 'all'
                || (state.groupFilter === '__ungrouped' && !groups.length)
                || groups.includes(state.groupFilter);
            const matched = groupMatched && (!query || searchable.includes(query)) && (statusFilter === 'all' || status === statusFilter);
            card.classList.toggle('is-filtered', !matched);
            if (matched) {
                visible += 1;
            }
        });
        dom.visibleCount.textContent = `显示 ${visible} / ${state.entries.length} 条`;
        dom.filterEmpty.classList.toggle('is-hidden', state.entries.length === 0 || visible > 0);
    }

    function syncCurrentOrder() {
        const order = Array.from(dom.playlist.children).map((card) => Number(card.dataset.index));
        if (order.some((index) => !Number.isInteger(index))) {
            return;
        }
        state.selected = new Set(order.reduce((selected, oldIndex, newIndex) => {
            if (state.selected.has(oldIndex)) {
                selected.push(newIndex);
            }
            return selected;
        }, []));
        state.checkScope = null;
        state.entries = order.map((index) => state.entries[index]);
        state.results = order.map((index) => state.results[index]);
        renderPlaylist();
        showToast('已更新播放顺序');
    }

    function removeEntry(index) {
        if (state.checking) {
            showToast('检查进行中，完成后再修改列表', 'info');
            return;
        }
        const selected = new Set();
        state.selected.forEach((selectedIndex) => {
            if (selectedIndex < index) {
                selected.add(selectedIndex);
            } else if (selectedIndex > index) {
                selected.add(selectedIndex - 1);
            }
        });
        state.selected = selected;
        state.checkScope = null;
        state.entries.splice(index, 1);
        state.results.splice(index, 1);
        updateGroupOptions();
        renderPlaylist();
        updateActionState();
        showToast('已从当前列表移除');
    }

    async function copyUrl(url) {
        let fallbackInput = null;
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(url);
            } else {
                fallbackInput = document.createElement('textarea');
                fallbackInput.value = url;
                fallbackInput.style.position = 'fixed';
                fallbackInput.style.opacity = '0';
                document.body.appendChild(fallbackInput);
                fallbackInput.select();
                if (!document.execCommand('copy')) {
                    throw new Error('当前浏览器不支持复制');
                }
            }
            showToast('播放地址已复制', 'success');
        } catch (error) {
            showToast(error.message || '复制失败', 'error');
        } finally {
            fallbackInput?.remove();
        }
    }

    function addDetailValue(container, label, value) {
        const item = document.createElement('div');
        item.className = 'detail-value';
        const labelNode = document.createElement('span');
        labelNode.textContent = label;
        const valueNode = document.createElement('strong');
        valueNode.textContent = text(value);
        item.append(labelNode, valueNode);
        container.appendChild(item);
    }

    function renderModalDetails(data, url) {
        const payload = data?.details || data || {};
        const available = data?.available ?? data?.status === 'ok';
        dom.videoInfoContent.replaceChildren();
        const address = document.createElement('p');
        address.className = 'dialog-url';
        address.textContent = text(url || payload.url, '地址未知');
        dom.videoInfoContent.appendChild(address);

        const summary = document.createElement('div');
        summary.className = 'detail-grid';
        addDetailValue(summary, '状态', available ? '可用' : '不可用');
        addDetailValue(summary, '探测方式', payload.method);
        addDetailValue(summary, '格式', payload.format);
        addDetailValue(summary, '时长', payload.duration);
        dom.videoInfoContent.appendChild(summary);

        if (payload.error) {
            const error = document.createElement('p');
            error.className = 'error-copy dialog-section';
            error.textContent = payload.error;
            dom.videoInfoContent.appendChild(error);
        }

        appendModalStreams('视频流', payload.video, 'video');
        appendModalStreams('音频流', payload.audio, 'audio');
        const playlistInfo = payload.playlist || {};
        if (Object.keys(playlistInfo).length) {
            const section = document.createElement('section');
            section.className = 'dialog-section';
            const heading = document.createElement('h3');
            heading.textContent = '播放列表信息';
            const grid = document.createElement('div');
            grid.className = 'detail-grid';
            Object.entries(playlistInfo).slice(0, 8).forEach(([key, value]) => addDetailValue(grid, key, value));
            section.append(heading, grid);
            dom.videoInfoContent.appendChild(section);
        }

        const rawDetails = document.createElement('details');
        rawDetails.className = 'raw-details';
        const rawSummary = document.createElement('summary');
        rawSummary.textContent = '查看原始 JSON';
        const raw = document.createElement('pre');
        raw.textContent = JSON.stringify(data, null, 2);
        rawDetails.append(rawSummary, raw);
        dom.videoInfoContent.appendChild(rawDetails);
    }

    function appendThumbnail(data) {
        if (data?.thumbnail) {
            const preview = document.createElement('figure');
            preview.className = 'thumbnail-preview';
            const image = document.createElement('img');
            image.src = data.thumbnail;
            image.alt = '视频首帧截图';
            image.loading = 'lazy';
            preview.appendChild(image);
            dom.videoInfoContent.appendChild(preview);
            return;
        }
        if (data?.thumbnail_error) {
            const message = document.createElement('p');
            message.className = 'result-hint thumbnail-error';
            message.textContent = '首帧截图不可用';
            message.title = data.thumbnail_error;
            dom.videoInfoContent.appendChild(message);
        }
    }

    async function loadThumbnail(url, controller, token) {
        try {
            const response = await fetchResponse('/thumbnail', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
                signal: controller.signal,
            }, '截取首帧');
            const data = await readJsonResponse(response);
            if (token === state.requestToken && dom.videoInfoModal.open) {
                appendThumbnail(data);
            }
        } catch (error) {
            if (error.name !== 'AbortError' && token === state.requestToken && dom.videoInfoModal.open) {
                appendThumbnail({ thumbnail_error: error.message || '首帧截图请求失败' });
            }
        }
    }

    function appendModalStreams(title, streams, type) {
        if (!streams?.length) {
            return;
        }
        const section = document.createElement('section');
        section.className = 'dialog-section';
        const heading = document.createElement('h3');
        heading.textContent = title;
        const list = document.createElement('div');
        list.className = 'stream-list';
        streams.forEach((stream, index) => {
            const row = document.createElement('div');
            row.className = 'stream-row';
            const label = document.createElement('span');
            label.className = 'stream-label';
            label.textContent = `#${index + 1}`;
            const value = document.createElement('span');
            value.className = 'stream-value';
            if (type === 'video') {
                value.textContent = [text(stream.codec), text(stream.resolution, '未知分辨率'), stream.frame_rate || ''].filter(Boolean).join(' · ');
            } else {
                value.textContent = [text(stream.codec), stream.sample_rate ? `${stream.sample_rate} Hz` : '', stream.channels ? `${stream.channels} 声道` : '', stream.channel_layout || stream.language || ''].filter(Boolean).join(' · ');
            }
            row.append(label, value);
            list.appendChild(row);
        });
        section.append(heading, list);
        dom.videoInfoContent.appendChild(section);
    }

    async function openDetails(index) {
        const entry = state.entries[index];
        if (!entry) {
            return;
        }
        const existing = state.results[index];
        dom.videoInfoTitle.textContent = text(entry.title, '视频信息');
        dom.videoInfoContent.replaceChildren();
        const loading = document.createElement('p');
        loading.className = 'result-hint';
        loading.textContent = existing ? '正在整理已有探测结果…' : '正在读取视频和音频信息…';
        dom.videoInfoContent.appendChild(loading);
        if (!dom.videoInfoModal.open) {
            dom.videoInfoModal.showModal();
        }
        state.infoController?.abort();
        const controller = new AbortController();
        state.infoController = controller;
        const token = state.requestToken;
        try {
            if (existing) {
                renderModalDetails(existing, entry.url);
                if (existing.status === 'ok') {
                    await loadThumbnail(entry.url, controller, token);
                }
            } else {
                const response = await fetchResponse('/video-info', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: entry.url }),
                    signal: controller.signal,
                }, '读取视频信息');
                const data = await readJsonResponse(response);
                if (token === state.requestToken) {
                    renderModalDetails(data, entry.url);
                    if (data.available) {
                        await loadThumbnail(entry.url, controller, token);
                    }
                }
            }
        } catch (error) {
            if (error.name !== 'AbortError' && token === state.requestToken) {
                renderModalDetails({ available: false, error: error.message || '获取信息失败' }, entry.url);
            }
        } finally {
            if (state.infoController === controller) {
                state.infoController = null;
            }
        }
    }

    async function readJsonResponse(response) {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.error) {
            throw new Error(data.error || `请求失败（${response.status}）`);
        }
        return data;
    }

    async function fetchResponse(url, options, action) {
        try {
            return await fetch(url, options);
        } catch (error) {
            if (error.name === 'AbortError') {
                throw error;
            }
            throw new Error(`${action}连接失败：请确认 Docker 服务正在运行，并检查网络代理`);
        }
    }

    function createDownload(blob, filename) {
        const objectUrl = window.URL.createObjectURL(blob);
        state.objectUrls.add(objectUrl);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => {
            window.URL.revokeObjectURL(objectUrl);
            state.objectUrls.delete(objectUrl);
        }, 1200);
    }

    async function downloadReport() {
        if (!state.sourceUrl || state.checking) {
            return;
        }
        dom.reportButton.disabled = true;
        state.reportController?.abort();
        const controller = new AbortController();
        state.reportController = controller;
        const token = state.requestToken;
        try {
            const response = await fetchResponse('/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: state.sourceUrl }),
                signal: controller.signal,
            }, '生成 HTML 报告');
            if (!response.ok) {
                await readJsonResponse(response);
            }
            createDownload(await response.blob(), 'm3u8-report.html');
            showToast('HTML 报告已下载', 'success');
        } catch (error) {
            if (error.name !== 'AbortError' && token === state.requestToken) {
                showToast(error.message || '报告生成失败', 'error');
            }
        } finally {
            if (state.reportController === controller) {
                state.reportController = null;
                updateActionState();
            }
        }
    }

    async function downloadPlaylist() {
        if (!state.entries.length || state.checking) {
            return;
        }
        dom.downloadButton.disabled = true;
        state.downloadController?.abort();
        const controller = new AbortController();
        state.downloadController = controller;
        const token = state.requestToken;
        try {
            const response = await fetchResponse('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries: state.entries }),
                signal: controller.signal,
            }, '导出播放列表');
            if (!response.ok) {
                await readJsonResponse(response);
            }
            createDownload(await response.blob(), 'playlist.m3u');
            showToast('M3U 文件已导出', 'success');
        } catch (error) {
            if (error.name !== 'AbortError' && token === state.requestToken) {
                showToast(error.message || '导出失败', 'error');
            }
        } finally {
            if (state.downloadController === controller) {
                state.downloadController = null;
                updateActionState();
            }
        }
    }

    async function runCheck(scopeIndexes) {
        if (!scopeIndexes.length || state.checking) {
            return;
        }
        state.checkScope = [...scopeIndexes];
        state.checking = true;
        state.stopRequested = false;
        scopeIndexes.forEach((index) => {
            state.results[index] = null;
        });
        updateCards();
        const workers = Number(dom.checkWorkers.value);
        const mode = workers === 1 ? '顺序检查' : `${workers} 路并发检查`;
        setConnection(`正在${mode}`, 'busy');
        setSourceState('检查进行中', 'busy');
        const controller = new AbortController();
        state.checkController = controller;
        const token = state.requestToken;
        try {
            const batchSize = Math.max(1, workers * 2);
            for (let start = 0; start < scopeIndexes.length; start += batchSize) {
                const batchIndexes = scopeIndexes.slice(start, start + batchSize);
                const batch = batchIndexes.map((index) => state.entries[index]);
                const response = await fetchResponse('/check-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ entries: batch, workers }),
                    signal: controller.signal,
                }, '批量检查');
                const data = await readJsonResponse(response);
                if (token !== state.requestToken) {
                    return;
                }
                if (!Array.isArray(data.results) || data.results.length !== batch.length) {
                    throw new Error('批量检查返回的结果数量不一致');
                }
                batchIndexes.forEach((index, offset) => {
                    state.results[index] = data.results[offset];
                });
                updateCards();
            }
            const available = scopeIndexes.filter((index) => state.results[index]?.status === 'ok').length;
            showToast(`检查完成：${available} / ${scopeIndexes.length} 条可用`, available ? 'success' : 'error');
        } catch (error) {
            if (error.name !== 'AbortError' && token === state.requestToken) {
                scopeIndexes.forEach((index) => {
                    state.results[index] = {
                        status: 'error',
                        details: { error: error.message || '批量检查失败' },
                    };
                });
                updateCards();
                showToast(error.message || '批量检查失败', 'error');
            }
        } finally {
            if (state.checkController === controller) {
                state.checkController = null;
            }
            if (token === state.requestToken) {
                const stopped = state.stopRequested;
                state.stopRequested = false;
                state.checking = false;
                updateCards();
                if (stopped) {
                    dom.progressTitle.textContent = '检查已停止';
                    dom.currentChecking.textContent = '已停止，已保留已完成结果';
                    setConnection('检查已停止');
                    setSourceState('已停止', 'loaded');
                } else {
                    setConnection('准备就绪');
                    setSourceState('已载入', 'loaded');
                }
            }
        }
    }

    function stopCheck() {
        if (!state.checking) {
            return;
        }
        state.stopRequested = true;
        state.checkController?.abort();
        updateActionState();
    }

    async function checkAll() {
        const scopeIndexes = getGroupIndexes();
        return runCheck(scopeIndexes);
    }

    async function checkSelected() {
        const scopeIndexes = Array.from(state.selected).sort((left, right) => left - right);
        return runCheck(scopeIndexes);
    }

    dom.form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const url = dom.urlInput.value.trim();
        const file = dom.fileInput.files[0];
        if (!url && !file) {
            showToast('请输入 M3U 地址或选择本地文件', 'error');
            return;
        }
        clearStaleState();
        const token = state.requestToken;
        const controller = new AbortController();
        state.parseController = controller;
        state.sourceUrl = url;
        setParsingState(true);
        setConnection('正在读取播放列表', 'busy');
        setSourceState('正在读取', 'busy');
        dom.sourceMeta.textContent = url ? '正在下载远程清单…' : `正在读取 ${file.name}`;
        const formData = new FormData();
        if (url) {
            formData.append('url', url);
        } else {
            formData.append('file', file);
        }
        try {
            const response = await fetchResponse('/parse', { method: 'POST', body: formData, signal: controller.signal }, '读取播放列表');
            const data = await readJsonResponse(response);
            if (token !== state.requestToken) {
                return;
            }
            if (!Array.isArray(data.entries) || !data.entries.length) {
                throw new Error('播放列表没有可展示的条目');
            }
            state.entries = data.entries;
            state.results = data.entries.map(() => null);
            state.groupFilter = 'all';
            updateGroupOptions();
            dom.dashboard.classList.remove('is-hidden');
            dom.sourceMeta.textContent = url ? `已载入远程清单 · ${data.entries.length} 条` : `${file.name} · ${data.entries.length} 条`;
            dom.fileName.textContent = file ? file.name : '选择本地文件';
            setSourceState('已载入', 'loaded');
            setConnection('准备就绪');
            renderPlaylist();
            showToast(`已载入 ${data.entries.length} 条播放地址`, 'success');
        } catch (error) {
            if (error.name !== 'AbortError' && token === state.requestToken) {
                setSourceState('读取失败', 'error');
                setConnection('读取失败', 'error');
                dom.sourceMeta.textContent = error.message || '播放列表读取失败';
                showToast(error.message || '播放列表读取失败', 'error');
            }
        } finally {
            if (state.parseController === controller) {
                state.parseController = null;
                setParsingState(false);
                updateActionState();
            }
        }
    });

    dom.fileInput.addEventListener('change', () => {
        const file = dom.fileInput.files[0];
        if (!file) {
            dom.fileName.textContent = '选择本地文件';
            return;
        }
        dom.urlInput.value = '';
        dom.fileName.textContent = file.name;
    });

    dom.urlInput.addEventListener('input', () => {
        if (dom.urlInput.value.trim()) {
            dom.fileInput.value = '';
            dom.fileName.textContent = '选择本地文件';
        }
    });

    dom.playlistSearch.addEventListener('input', applyFilters);
    dom.statusFilter.addEventListener('change', applyFilters);
    dom.groupFilter.addEventListener('change', () => {
        state.groupFilter = dom.groupFilter.value;
        state.checkScope = null;
        applyFilters();
        updateSummary();
        updateProgress();
        updateActionState();
    });
    dom.checkAllButton.addEventListener('click', checkAll);
    dom.checkSelectedButton.addEventListener('click', checkSelected);
    dom.stopCheckButton.addEventListener('click', stopCheck);
    dom.reportButton.addEventListener('click', downloadReport);
    dom.downloadButton.addEventListener('click', downloadPlaylist);
    dom.closeModalButton.addEventListener('click', () => dom.videoInfoModal.close());
    dom.videoInfoModal.addEventListener('click', (event) => {
        if (event.target === dom.videoInfoModal) {
            dom.videoInfoModal.close();
        }
    });
    dom.videoInfoModal.addEventListener('close', () => {
        state.infoController?.abort();
        dom.videoInfoContent.replaceChildren();
    });

    clearStaleState();
});
