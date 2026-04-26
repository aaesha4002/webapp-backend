(() => {
    const hideForm = document.getElementById('hide-form');
    const revealForm = document.getElementById('reveal-form');
    const hideResult = document.getElementById('hide-result');
    const revealResult = document.getElementById('reveal-result');
    const payloadModeRadios = document.querySelectorAll('input[name="payload-mode"]');
    const payloadTextGroup = document.getElementById('payload-text-group');
    const payloadFileGroup = document.getElementById('payload-file-group');
    const payloadFileLabel = document.getElementById('payload-file-label');
    const coverInput = hideForm?.querySelector('input[name="cover"]');
    const coverPreview = document.querySelector('#cover-preview img');
    const coverPlaceholder = document.querySelector('#cover-preview .placeholder');
    const revealPreview = document.querySelector('#reveal-preview img');
    const revealAudio = document.querySelector('#reveal-preview audio');
    const revealText = document.querySelector('#reveal-preview pre');
    const revealPlaceholder = document.querySelector('#reveal-preview .placeholder');

    const setResult = (el, state, message, link) => {
        el.dataset.state = state;
        if (link) {
            el.innerHTML = `<span>${message}</span> <a download="${link.filename}" href="${link.url}">Download</a>`;
        } else {
            el.textContent = message;
        }
    };

    const switchPayload = (mode) => {
        payloadTextGroup.classList.toggle('hidden', mode !== 'text');
        payloadFileGroup.classList.toggle('hidden', mode === 'text');
        const fileInput = payloadFileGroup.querySelector('input[name="payload_file"]');
        fileInput.value = '';
        if (mode === 'image') {
            payloadFileLabel.textContent = 'Payload image';
            fileInput.accept = 'image/*';
        } else if (mode === 'audio') {
            payloadFileLabel.textContent = 'Payload audio';
            fileInput.accept = 'audio/*';
        } else {
            payloadFileLabel.textContent = 'Payload file';
            fileInput.accept = '';
        }
    };

    const showCoverPreview = (file) => {
        if (!file) {
            coverPreview.classList.add('hidden');
            coverPlaceholder.classList.remove('hidden');
            return;
        }
        const url = URL.createObjectURL(file);
        coverPreview.src = url;
        coverPreview.classList.remove('hidden');
        coverPlaceholder.classList.add('hidden');
    };

    const resetRevealPreview = () => {
        revealPreview.classList.add('hidden');
        revealAudio.pause();
        revealAudio.src = '';
        revealAudio.classList.add('hidden');
        revealText.classList.add('hidden');
        revealText.textContent = '';
        revealPlaceholder.classList.remove('hidden');
    };

    const showRevealImage = (url, filename) => {
        // Cache buster prevents WebView from locking the socket
        revealPreview.src = url + '?t=' + Date.now();
        revealPreview.alt = filename;
        revealPreview.classList.remove('hidden');
        revealText.classList.add('hidden');
        revealAudio.classList.add('hidden');
        revealPlaceholder.classList.add('hidden');
    };

    const showRevealAudio = (url, filename) => {
        revealAudio.src = url + '?t=' + Date.now();
        revealAudio.classList.remove('hidden');
        revealPreview.classList.add('hidden');
        revealText.classList.add('hidden');
        revealPlaceholder.classList.add('hidden');
    };

    const showRevealText = async (url, filename) => {
        try {
            const res = await fetch(url + '?t=' + Date.now());
            const text = await res.text();
            revealText.textContent = text;
            revealText.classList.remove('hidden');
            revealPreview.classList.add('hidden');
            revealAudio.classList.add('hidden');
            revealPlaceholder.classList.add('hidden');
        } catch (err) {
            revealPlaceholder.textContent = `Retrieved ${filename}; open via download to view.`;
            revealPlaceholder.classList.remove('hidden');
            revealPreview.classList.add('hidden');
            revealAudio.classList.add('hidden');
            revealText.classList.add('hidden');
        }
    };

    payloadModeRadios.forEach((radio) => {
        radio.addEventListener('change', (event) => {
            if (event.target.checked) switchPayload(event.target.value);
        });
    });

    switchPayload('text');

    coverInput?.addEventListener('change', (event) => {
        const file = event.target.files[0];
        showCoverPreview(file);
    });

    hideForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const formData = new FormData();
        const cover = hideForm.querySelector('input[name="cover"]').files[0];
        const mode = hideForm.querySelector('input[name="payload-mode"]:checked').value;
        const alias = hideForm.querySelector('input[name="alias"]').value.trim();
        const key = hideForm.querySelector('input[name="key"]').value;

        if (!cover) {
            setResult(hideResult, 'error', 'Select a cover image to embed into.');
            return;
        }

        formData.append('cover', cover);

        if (mode === 'text') {
            const text = hideForm.querySelector('textarea[name="payload_text"]').value.trim();
            if (!text) {
                setResult(hideResult, 'error', 'Add the secret text to embed.');
                return;
            }
            formData.append('payload_text', text);
        } else {
            const file = hideForm.querySelector('input[name="payload_file"]').files[0];
            if (!file) {
                let label = 'payload file';
                if (mode === 'image') label = 'payload image';
                if (mode === 'audio') label = 'payload audio';
                setResult(hideResult, 'error', `Choose a ${label} to embed.`);
                return;
            }
            formData.append('payload_file', file);
        }

        if (alias) formData.append('alias', alias);
        if (key) formData.append('key', key);

        setResult(hideResult, 'pending', 'Embedding payload...');

        try {
            const response = await fetch('/api/hide', { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || 'Unable to generate stego image.');
            }
            
            const url = data.image;
            const filename = 'stego.png';
            setResult(hideResult, 'success', `Ready: ${filename}`, { url, filename });
        } catch (error) {
            setResult(hideResult, 'error', error.message);
        }
    });

    revealForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        resetRevealPreview();
        const formData = new FormData();
        const stego = revealForm.querySelector('input[name="stego"]').files[0];
        const key = revealForm.querySelector('input[name="key"]').value;

        if (!stego) {
            setResult(revealResult, 'error', 'Select the stego image to inspect.');
            return;
        }

        formData.append('stego', stego);
        if (key) formData.append('key', key);

        setResult(revealResult, 'pending', 'Retrieving payload...');

        try {
            const response = await fetch('/api/retrieve', { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || 'Unable to retrieve payload.');
            }
            
            const url = data.image || data.file_url;
            const filename = data.filename || 'recovered.bin';

            const ext = filename.split('.').pop().toLowerCase();
            const isImage = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'].includes(ext);
            const isAudio = ['mp3', 'wav', 'flac', 'ogg', 'oga', 'opus', 'aac', 'm4a'].includes(ext);
            const isText = ['txt', 'md', 'json', 'yaml', 'yml', 'csv', 'log'].includes(ext);

            if (isImage) {
                showRevealImage(url, filename);
            } else if (isAudio) {
                showRevealAudio(url, filename);
            } else if (isText) {
                await showRevealText(url, filename);
            } else {
                revealPlaceholder.textContent = `Retrieved ${filename}; download to view.`;
                revealPlaceholder.classList.remove('hidden');
                revealPreview.classList.add('hidden');
                revealAudio.classList.add('hidden');
                revealText.classList.add('hidden');
            }

            setResult(revealResult, 'success', `Retrieved: ${filename}`, { url, filename });
        } catch (error) {
            resetRevealPreview();
            setResult(revealResult, 'error', error.message);
        }
    });

    // ── Mode switcher ─────────────────────────────────────────────────────────
    const btnLsb    = document.getElementById('btn-lsb');
    const btnAi     = document.getElementById('btn-ai');
    const lsbPanels = document.getElementById('lsb-panels');
    const aiPanels  = document.getElementById('ai-panels');

    const switchMode = (mode) => {
        const isAi = mode === 'ai';
        btnLsb.classList.toggle('active', !isAi);
        btnAi.classList.toggle('active', isAi);
        lsbPanels.classList.toggle('hidden', isAi);
        aiPanels.classList.toggle('hidden', !isAi);
    };

    btnLsb?.addEventListener('click', () => switchMode('lsb'));
    btnAi?.addEventListener('click',  () => switchMode('ai'));

    // ── AI cover / secret previews ────────────────────────────────────────────
    const aiHideForm      = document.getElementById('ai-hide-form');
    const aiExtractForm   = document.getElementById('ai-extract-form');
    const aiHideResult    = document.getElementById('ai-hide-result');
    const aiExtractResult = document.getElementById('ai-extract-result');

    const aiCoverImg   = document.querySelector('#ai-cover-preview img');
    const aiCoverPh    = document.querySelector('#ai-cover-preview .placeholder');
    const aiSecretImg  = document.querySelector('#ai-secret-preview img');
    const aiSecretPh   = document.querySelector('#ai-secret-preview .placeholder');
    const aiRevealImg  = document.querySelector('#ai-extract-preview img');
    const aiRevealPh   = document.querySelector('#ai-extract-preview .placeholder');

    const showPreview = (imgEl, phEl, file) => {
        if (!file) { imgEl.classList.add('hidden'); phEl.classList.remove('hidden'); return; }
        const url = URL.createObjectURL(file);
        imgEl.src = url;
        imgEl.classList.remove('hidden');
        phEl.classList.add('hidden');
    };

    aiHideForm?.querySelector('input[name="cover"]')
        ?.addEventListener('change', (e) => showPreview(aiCoverImg, aiCoverPh, e.target.files[0]));

    aiHideForm?.querySelector('input[name="secret"]')
        ?.addEventListener('change', (e) => showPreview(aiSecretImg, aiSecretPh, e.target.files[0]));

    // ── AI Hide submit ────────────────────────────────────────────────────────
    aiHideForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const cover  = aiHideForm.querySelector('input[name="cover"]').files[0];
        const secret = aiHideForm.querySelector('input[name="secret"]').files[0];
        if (!cover)  { setResult(aiHideResult, 'error', 'Select a cover image.'); return; }
        if (!secret) { setResult(aiHideResult, 'error', 'Select a secret image to embed.'); return; }

        const formData = new FormData();
        formData.append('cover', cover);
        formData.append('secret', secret);

        setResult(aiHideResult, 'pending', 'Running AI encoder…');
        try {
            const response = await fetch('/api/ai-hide', { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || 'AI encoding failed.');
            }
            
            const url = data.image;
            const filename = 'ai_container.png';
            setResult(aiHideResult, 'success', `Ready: ${filename}`, { url, filename });
        } catch (err) {
            setResult(aiHideResult, 'error', err.message);
        }
    });

    // ── AI Extract submit ─────────────────────────────────────────────────────
    aiExtractForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const container = aiExtractForm.querySelector('input[name="container"]').files[0];
        if (!container) { setResult(aiExtractResult, 'error', 'Select a container image.'); return; }

        // Reset preview
        aiRevealImg.classList.add('hidden');
        aiRevealPh.classList.remove('hidden');
        aiRevealPh.textContent = 'Revealed image will appear here';

        const formData = new FormData();
        formData.append('container', container);

        setResult(aiExtractResult, 'pending', 'Running AI decoder…');
        try {
            const response = await fetch('/api/ai-extract', { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || 'AI extraction failed.');
            }
            
            const url = data.image;
            const filename = 'ai_revealed.png';

            // Show inline preview (with cache buster)
            aiRevealImg.src = url + '?t=' + Date.now();
            aiRevealImg.alt = filename;
            aiRevealImg.classList.remove('hidden');
            aiRevealPh.classList.add('hidden');

            setResult(aiExtractResult, 'success', `Revealed: ${filename}`, { url, filename });
        } catch (err) {
            setResult(aiExtractResult, 'error', err.message);
        }
    });

    // ── AI sub-mode switcher (Image in Image ↔ Text in Image) ────────────────
    const btnAiImg   = document.getElementById('btn-ai-img');
    const btnAiTxt   = document.getElementById('btn-ai-txt');
    const aiImgPanels = document.getElementById('ai-img-panels');
    const aiTxtPanels = document.getElementById('ai-txt-panels');

    const switchAiSubMode = (mode) => {
        const isText = mode === 'text';
        btnAiImg.classList.toggle('active', !isText);
        btnAiTxt.classList.toggle('active', isText);
        aiImgPanels.classList.toggle('hidden', isText);
        aiTxtPanels.classList.toggle('hidden', !isText);
    };

    btnAiImg?.addEventListener('click', () => switchAiSubMode('image'));
    btnAiTxt?.addEventListener('click', () => switchAiSubMode('text'));

    // ── AI Text Hide ──────────────────────────────────────────────────────────
    const aiTextHideForm    = document.getElementById('ai-text-hide-form');
    const aiTextExtractForm = document.getElementById('ai-text-extract-form');
    const aiTextHideResult    = document.getElementById('ai-text-hide-result');
    const aiTextExtractResult = document.getElementById('ai-text-extract-result');

    const aiTxtCoverImg = document.querySelector('#ai-txt-cover-preview img');
    const aiTxtCoverPh  = document.querySelector('#ai-txt-cover-preview .placeholder');
    const aiTxtExtractPre = document.querySelector('#ai-text-extract-preview pre');
    const aiTxtExtractPh  = document.querySelector('#ai-text-extract-preview .placeholder');

    // Character counter
    const aiTxtTextarea  = aiTextHideForm?.querySelector('textarea[name="text"]');
    const aiTxtCharCount = document.getElementById('ai-txt-char-count');
    aiTxtTextarea?.addEventListener('input', () => {
        const len = aiTxtTextarea.value.length;
        aiTxtCharCount.textContent = `(${len} / 50)`;
    });

    aiTextHideForm?.querySelector('input[name="cover"]')
        ?.addEventListener('change', (e) => showPreview(aiTxtCoverImg, aiTxtCoverPh, e.target.files[0]));

    aiTextHideForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const cover = aiTextHideForm.querySelector('input[name="cover"]').files[0];
        const text  = aiTxtTextarea.value.trim();
        if (!cover) { setResult(aiTextHideResult, 'error', 'Select a cover image.'); return; }
        if (!text)  { setResult(aiTextHideResult, 'error', 'Enter a secret message.'); return; }

        const formData = new FormData();
        formData.append('cover', cover);
        formData.append('text', text);

        setResult(aiTextHideResult, 'pending', 'Running AI text encoder…');
        try {
            const response = await fetch('/api/ai-text-hide', { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || 'AI text encoding failed.');
            }
            
            const url = data.image;
            const filename = 'ai_text_container.png';
            setResult(aiTextHideResult, 'success', `Ready: ${filename}`, { url, filename });
        } catch (err) {
            setResult(aiTextHideResult, 'error', err.message);
        }
    });

    // ── AI Text Extract ───────────────────────────────────────────────────────
    aiTextExtractForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const stego = aiTextExtractForm.querySelector('input[name="stego"]').files[0];
        if (!stego) { setResult(aiTextExtractResult, 'error', 'Select a stego image.'); return; }

        // Reset preview
        aiTxtExtractPre.classList.add('hidden');
        aiTxtExtractPre.textContent = '';
        aiTxtExtractPh.classList.remove('hidden');
        aiTxtExtractPh.textContent = 'Extracted text will appear here';

        const formData = new FormData();
        formData.append('stego', stego);

        setResult(aiTextExtractResult, 'pending', 'Running AI text decoder…');
        try {
            const response = await fetch('/api/ai-text-extract', { method: 'POST', body: formData });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || 'AI text extraction failed.');
            }
            
            aiTxtExtractPre.textContent = data.text || '(empty)';
            aiTxtExtractPre.classList.remove('hidden');
            aiTxtExtractPh.classList.add('hidden');
            setResult(aiTextExtractResult, 'success', 'Text recovered successfully.');
        } catch (err) {
            setResult(aiTextExtractResult, 'error', err.message);
        }
    });
})();
