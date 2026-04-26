(function () {
    'use strict';

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

    function formatMoney(value) {
        return Number(value || 0).toFixed(2);
    }

    function secondsRemaining(endsAt) {
        if (!endsAt) {
            return 0;
        }
        return Math.max(0, Math.floor((new Date(endsAt.replace(' ', 'T') + 'Z').getTime() - Date.now()) / 1000));
    }

    function formatTimer(seconds) {
        return String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
    }

    function setWinning(node, winning) {
        if (!node) {
            return;
        }
        node.classList.toggle('is-winning', Boolean(winning));
        node.classList.toggle('is-losing', !winning);
        node.title = winning ? 'Currently best' : 'Behind best other offer';
    }

    const bootstrapNode = document.getElementById('o_tender_bootstrap');
    if (bootstrapNode) {
        const config = JSON.parse(bootstrapNode.textContent || '{}');
        const root = bootstrapNode.closest('.o_tender_live');
        const countdownNode = root && root.querySelector('[data-role="countdown"]');
        const submitButton = root && root.querySelector('.o_tender_submit_live');

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
            const remaining = secondsRemaining(config.ends_at);
            countdownNode.textContent = formatTimer(remaining);
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
                const deliveryInput = root.querySelector('.o_tender_delivery_input[data-line-id="' + input.dataset.lineId + '"]');
                return {
                    line_id: Number(input.dataset.lineId),
                    price_unit: Number(input.value || 0),
                    delivery_days: Number(deliveryInput && deliveryInput.value || 0),
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
    }

    const dashboardNode = document.getElementById('o_tender_dashboard_bootstrap');
    if (!dashboardNode) {
        return;
    }
    const dashboardConfig = JSON.parse(dashboardNode.textContent || '{}');
    const dashboardRoot = dashboardNode.closest('.o_tender_dashboard');

    function renderDashboard(snapshot) {
        const overall = dashboardRoot.querySelector('.o_tender_dashboard_overall');
        const lines = dashboardRoot.querySelector('.o_tender_dashboard_lines');
        const history = dashboardRoot.querySelector('.o_tender_dashboard_history');
        const timer = dashboardRoot.querySelector('.o_tender_dashboard_timer');
        const chart = dashboardRoot.querySelector('.o_tender_dashboard_chart');
        if (timer && snapshot.ends_at) {
            timer.textContent = formatTimer(secondsRemaining(snapshot.ends_at));
        }
        overall.innerHTML = (snapshot.bidders || []).map(function (bidder, index) {
            const width = snapshot.best_total && bidder.total_amount ? Math.max(8, (snapshot.best_total / bidder.total_amount) * 100) : 0;
            return '<div class="o_tender_rank_row">' +
                '<div class="d-flex justify-content-between"><strong>#' + (index + 1) + ' ' + bidder.vendor + '</strong><span>' + formatMoney(bidder.total_amount) + ' (' + formatDelta(bidder.delta_percent) + ')</span></div>' +
                '<div class="o_tender_bar"><span style="width:' + width + '%"></span></div>' +
                '<div class="text-muted small">' + bidder.bid_count + ' bids, max delivery: ' + bidder.delivery_days + ' days, last: ' + (bidder.last_bid_at || '-') + '</div>' +
            '</div>';
        }).join('');
        lines.innerHTML = (snapshot.lines || []).map(function (line) {
            const rows = (line.bidders || []).map(function (bidder) {
                return '<tr><td>' + bidder.vendor + '</td><td class="text-end">' + formatMoney(bidder.price_unit) + '</td><td class="text-end">' + bidder.delivery_days + '</td><td class="text-end">' + formatDelta(bidder.delta_percent) + '</td><td class="text-center">' + (bidder.is_best ? '*' : '') + '</td></tr>';
            }).join('');
            return '<div class="o_tender_line_panel"><div class="d-flex justify-content-between"><strong>' + line.product_name + '</strong><span>Best: ' + formatMoney(line.best_price) + '</span></div>' +
                '<table class="table table-sm mb-0"><thead><tr><th>Vendor</th><th class="text-end">Item Price</th><th class="text-end">Delivery</th><th class="text-end">Vs Best</th><th class="text-center">Best</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
        }).join('');
        history.innerHTML = '<table class="table table-sm"><thead><tr><th>Time</th><th>Vendor</th><th>Kind</th><th class="text-end">Total</th></tr></thead><tbody>' +
            (snapshot.history || []).map(function (bid) {
                return '<tr><td>' + bid.submitted_at + '</td><td>' + bid.vendor + '</td><td>' + bid.submission_kind + '</td><td class="text-end">' + formatMoney(bid.total_amount) + '</td></tr>';
            }).join('') + '</tbody></table>';
        drawDashboardChart(chart, snapshot.bidders || []);
    }

    function drawDashboardChart(canvas, bidders) {
        if (!canvas) {
            return;
        }
        const width = canvas.clientWidth || 640;
        const height = Number(canvas.getAttribute('height')) || 220;
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, width, height);
        ctx.font = '12px sans-serif';
        ctx.fillStyle = '#212529';
        const max = Math.max.apply(null, bidders.map(function (bidder) { return bidder.total_amount || 0; }).concat([1]));
        const gap = 16;
        const barWidth = Math.max(24, (width - gap * (bidders.length + 1)) / Math.max(1, bidders.length));
        bidders.forEach(function (bidder, index) {
            const barHeight = Math.max(4, ((bidder.total_amount || 0) / max) * (height - 58));
            const x = gap + index * (barWidth + gap);
            const y = height - 34 - barHeight;
            ctx.fillStyle = bidder.is_best ? '#14883d' : '#6f4e7c';
            ctx.fillRect(x, y, barWidth, barHeight);
            ctx.fillStyle = '#212529';
            ctx.fillText(formatMoney(bidder.total_amount), x, Math.max(12, y - 6));
            ctx.fillText(String(bidder.vendor || '').slice(0, 16), x, height - 12);
        });
    }

    function pollDashboard() {
        return jsonRpc(dashboardConfig.poll_url, {}).then(renderDashboard);
    }
    pollDashboard();
    setInterval(pollDashboard, 5000);
}());
