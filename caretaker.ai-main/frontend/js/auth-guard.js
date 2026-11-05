/**
 * auth-guard.js — load FIRST on every signed-in page.
 *
 * Problem it fixes: login tokens expire, and most pages swallowed the 401
 * responses, so dashboards just looked empty ("backend doesn't fetch data").
 * Now any 401 from the CareTaker API shows a clear message and sends the user
 * back to sign in, then returns them to the page they were on.
 *
 * It also warns when the page's address differs from the one used to log in
 * (localhost vs 127.0.0.1 keep separate storage, so the token "disappears").
 */
(function () {
    'use strict';
    const API_HOSTS = ['127.0.0.1:8000', 'localhost:8000'];
    const OPEN_PATHS = ['/login', '/signup', '/register', '/token'];
    let redirecting = false;

    function getToken() {
        try { return sessionStorage.getItem('token') || localStorage.getItem('token'); } catch (e) { return null; }
    }

    function tokenExpiry(tok) {
        try {
            const p = JSON.parse(atob(tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
            return p.exp ? p.exp * 1000 : null;
        } catch (e) { return null; }
    }

    function banner(text) {
        if (document.getElementById('auth-guard-banner')) return;
        const show = () => {
            const b = document.createElement('div');
            b.id = 'auth-guard-banner';
            b.setAttribute('role', 'alert');
            b.style.cssText = 'position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:100000;' +
                'background:#1F2A4D;color:#fff;padding:12px 18px;border-radius:12px;font:600 15px system-ui,sans-serif;' +
                'box-shadow:0 10px 30px rgba(0,0,0,.25);max-width:calc(100% - 32px)';
            b.textContent = text;
            document.body.appendChild(b);
        };
        document.body ? show() : document.addEventListener('DOMContentLoaded', show);
    }

    function sessionExpired() {
        if (redirecting) return;
        redirecting = true;
        try { localStorage.removeItem('token'); sessionStorage.removeItem('token'); } catch (e) { /* ignore */ }
        banner('Your sign-in has expired. Taking you to the login page…');
        const back = encodeURIComponent(location.pathname.split('/').pop() + location.search);
        setTimeout(() => { location.href = 'login.html?next=' + back; }, 1800);
    }
    window.caretakerSessionExpired = sessionExpired;

    const isApi = (url) => API_HOSTS.some(h => url.includes(h)) && !OPEN_PATHS.some(p => url.includes(p));

    const origFetch = window.fetch.bind(window);
    window.fetch = async function (input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const res = await origFetch(input, init);
        if (res.status === 401 && isApi(url)) sessionExpired();
        return res;
    };

    // Expired before the page even loads → don't render an empty dashboard
    const tok = getToken();
    const exp = tok ? tokenExpiry(tok) : null;
    if (exp && exp < Date.now()) sessionExpired();
    else if (exp) setTimeout(sessionExpired, Math.max(0, exp - Date.now()) + 1000);

    if (!tok && /(^|\/)(dashboard|voice_bot|video_monitoring|audio_monitoring|profile|insights|settings|saathi_profile|medical_reports)\.html$/.test(location.pathname)) {
        const other = location.hostname === 'localhost' ? '127.0.0.1' : location.hostname === '127.0.0.1' ? 'localhost' : null;
        banner(other
            ? `You're not signed in on ${location.hostname}. If you logged in at ${other}, open this page there (they keep separate logins).`
            : 'Please sign in first.');
    }
})();
