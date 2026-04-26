(function () {
    'use strict';

    const bootstrapNode = document.getElementById('o_tender_bootstrap');
    if (!bootstrapNode) {
        return;
    }

    const config = JSON.parse(bootstrapNode.textContent || '{}');
    const root = bootstrapNode.closest('.o_tender_live');
    const countdownNode = root && root.querySelector('[data-role="countdown"]');
    const submitButton = root && root.querySelector('.o_tender_submit_live');

    function jsonRpc(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin',
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: params || {},
                id: Date.now(),
            }),
        }).then(function (response) {
            return response.json();
        }).then(function (payload) {
            if (payload.error) {
                throw new Error(payload.error.data && payload.error.data.message || payload.error.message);
            }
            return payload.result;
        });
    }

    function formatDelta(value) {
        const number = Number(value || 0);
        const sign = number > 0 ? '+' : '';
        return sign + number.toFixed(2) + '%';
    }

    function setWinning(node, winning) {
        if (!node) {
            return;
        }
        node.classList.toggle('is-winning', Boolean(winning));
        node.classList.toggle('is-losing', !winning);
        node.title = winning ? 'Currently best' : 'Behind best other offer';
    }

    function renderSnapshot(snapshot) {
        (snapshot.lines || []).forEach(function (line) {
            const delta = root.querySelector('.o_tender_delta[data-line-id="' + line.line_id + '"]');
            const winning = root.querySelector('.o_tender_is_winning[data-line-id="' + line.line_id + '"]');
            if (delta) {
                delta.textContent = formatDelta(line.delta_percent);
                delta.classList.toggle('is-winning', line.is_currently_winning);
                delta.classList.toggle('is-losing', !line.is_currently_winning);
            }
            setWinning(winning, line.is_currently_winning);
        });
        if (snapshot.overall) {
            const overallDelta = root.querySelector('.o_tender_overall_delta');
            const overallWinning = root.querySelector('.o_tender_overall_winning');
            if (overallDelta) {
                overallDelta.textContent = formatDelta(snapshot.overall.delta_percent);
                overallDelta.classList.toggle('is-winning', snapshot.overall.is_currently_winning);
                overallDelta.classList.toggle('is-losing', !snapshot.overall.is_currently_winning);
            }
            setWinning(overallWinning, snapshot.overall.is_currently_winning);
        }
    }

    function renderCountdown() {
        if (!countdownNode || !config.ends_at) {
            return;
        }
        const end = new Date(config.ends_at.replace(' ', 'T') + 'Z').getTime();
        const remaining = Math.max(0, Math.floor((end - Date.now()) / 1000));
        const minutes = Math.floor(remaining / 60);
        const seconds = remaining % 60;
        countdownNode.textContent = String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
        if (!remaining) {
            countdownNode.classList.remove('text-bg-dark');
            countdownNode.classList.add('text-bg-secondary');
            if (submitButton) {
                submitButton.disabled = true;
            }
        }
    }

    function poll() {
        return jsonRpc(config.poll_url, {access_token: config.access_token}).then(renderSnapshot);
    }

    function submitLive() {
        const lines = Array.from(root.querySelectorAll('.o_tender_price_input')).map(function (input) {
            return {
                line_id: Number(input.dataset.lineId),
                price_unit: Number(input.value || 0),
            };
        });
        submitButton.disabled = true;
        jsonRpc(config.submit_url, {
            access_token: config.access_token,
            lines: lines,
        }).then(renderSnapshot).finally(function () {
            submitButton.disabled = false;
        });
    }

    if (submitButton) {
        submitButton.addEventListener('click', submitLive);
    }
    poll();
    renderCountdown();
    setInterval(poll, 5000);
    setInterval(renderCountdown, 1000);
}());
