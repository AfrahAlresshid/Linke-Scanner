(function (global) {
    'use strict';

    var DEFAULT_MS = 4800;
    var ICONS = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    function ensureHost() {
        var el = document.getElementById('link-notify-host');
        if (!el) {
            el = document.createElement('div');
            el.id = 'link-notify-host';
            el.className = 'link-notify-host';
            el.setAttribute('aria-live', 'polite');
            document.body.appendChild(el);
        }
        return el;
    }

    function show(message, type, durationMs) {
        if (!message) {
            return;
        }
        type = type || 'info';
        if (!ICONS[type]) {
            type = 'info';
        }
        var ms = durationMs == null ? DEFAULT_MS : durationMs;
        var host = ensureHost();
        var el = document.createElement('div');
        el.className = 'link-notify link-notify--' + type;
        el.setAttribute('role', 'status');
        el.innerHTML =
            '<span class="link-notify__icon" aria-hidden="true"><i class="fa ' + ICONS[type] + '"></i></span>' +
            '<span class="link-notify__text"></span>' +
            '<button type="button" class="link-notify__dismiss" aria-label="Close"><i class="fa fa-times"></i></button>';
        el.querySelector('.link-notify__text').textContent = message;
        host.appendChild(el);

        requestAnimationFrame(function () {
            el.classList.add('link-notify--visible');
        });

        var timer = null;

        function dismiss() {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            el.classList.remove('link-notify--visible');
            el.classList.add('link-notify--leaving');
            setTimeout(function () {
                if (el.parentNode) {
                    el.parentNode.removeChild(el);
                }
            }, 320);
        }

        timer = setTimeout(dismiss, ms);

        var btn = el.querySelector('.link-notify__dismiss');
        if (btn) {
            btn.addEventListener('click', function () {
                dismiss();
            });
        }

        return el;
    }

    global.LinkNotify = { show: show };
})(typeof window !== 'undefined' ? window : this);
