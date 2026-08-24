document.addEventListener("DOMContentLoaded", () => {
    // ===============================
    // Theme Toggle (Claro / Escuro)
    // ===============================
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon   = document.getElementById('theme-icon');
    const html        = document.documentElement;

    function applyTheme(theme) {
        html.setAttribute('data-theme', theme);
        try { localStorage.setItem('cinnamon-theme', theme); } catch(e) {}
        if (themeIcon) {
            themeIcon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        }
        if (themeToggle) {
            themeToggle.title = theme === 'dark' ? 'Mudar para modo claro' : 'Mudar para modo escuro';
        }
        // Troca favicon conforme tema
        const favicon = document.getElementById('favicon');
        if (favicon) {
            const base = favicon.href.substring(0, favicon.href.lastIndexOf('/') + 1);
            favicon.href = theme === 'light'
                ? base + 'simbolo-logo-lightmode.png'
                : base + 'simbolo-logo-darkmode.png';
        }
    }

    // Inicializa ícone conforme tema atual (já aplicado pelo script inline no <head>)
    const currentTheme = html.getAttribute('data-theme') || 'light';
    applyTheme(currentTheme);

    if (themeToggle) {
        themeToggle.addEventListener('click', function () {
            const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            applyTheme(next);
        });
    }

    // ===============================
    // Navbar user dropdown toggle
    // ===============================
    document.querySelectorAll('.site-nav__user-btn[data-dropdown]').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var targetId = btn.getAttribute('data-dropdown');
            var dropdown = document.getElementById(targetId);
            if (!dropdown) return;
            var isOpen = dropdown.classList.contains('show');
            // close all open dropdowns first
            document.querySelectorAll('.site-nav__dropdown.show').forEach(function (d) {
                d.classList.remove('show');
            });
            document.querySelectorAll('.site-nav__user-btn').forEach(function (b) {
                b.setAttribute('aria-expanded', 'false');
            });
            if (!isOpen) {
                dropdown.classList.add('show');
                btn.setAttribute('aria-expanded', 'true');
            }
        });
    });

    // close on outside click
    document.addEventListener('click', function () {
        document.querySelectorAll('.site-nav__dropdown.show').forEach(function (d) {
            d.classList.remove('show');
        });
        document.querySelectorAll('.site-nav__user-btn').forEach(function (b) {
            b.setAttribute('aria-expanded', 'false');
        });
    });

    // ===============================
    // Mobile drawer (hamburger) menu
    // ===============================
    const mobileToggle = document.querySelector('.site-nav__toggle');
    const mobileMenu = document.querySelector('.site-nav__links');
    const mobileBackdrop = document.querySelector('.site-nav__backdrop');
    const mobileClose = document.querySelector('.site-nav__drawer-close');
    const DRAWER_BREAKPOINT = 1200; // keep in sync with the CSS max-width: 1199.98px cutover
    const BACKDROP_TRANSITION_MS = 250;

    if (mobileToggle && mobileMenu) {
        const isMobile = () => window.innerWidth < DRAWER_BREAKPOINT;
        const isDrawerOpen = () => mobileMenu.classList.contains('is-open');
        const getFocusable = () => mobileMenu.querySelectorAll(
            'a[href], button:not([disabled]), select, input, [tabindex]:not([tabindex="-1"])'
        );

        function syncInert() {
            if (isMobile() && !isDrawerOpen()) {
                mobileMenu.setAttribute('inert', '');
            } else {
                mobileMenu.removeAttribute('inert');
            }
        }

        function openDrawer() {
            mobileMenu.classList.add('is-open');
            mobileMenu.removeAttribute('inert');
            mobileToggle.setAttribute('aria-expanded', 'true');
            const icon = mobileToggle.querySelector('i');
            if (icon) icon.className = 'bi bi-x-lg';
            document.body.classList.add('site-nav-open');
            if (mobileBackdrop) {
                mobileBackdrop.hidden = false;
                requestAnimationFrame(() => mobileBackdrop.classList.add('is-open'));
            }
            const focusable = getFocusable();
            if (focusable.length) focusable[0].focus();
        }

        function closeDrawer(options) {
            const returnFocus = !options || options.returnFocus !== false;
            mobileMenu.classList.remove('is-open');
            mobileToggle.setAttribute('aria-expanded', 'false');
            const icon = mobileToggle.querySelector('i');
            if (icon) icon.className = 'bi bi-list';
            document.body.classList.remove('site-nav-open');
            if (mobileBackdrop) {
                mobileBackdrop.classList.remove('is-open');
                setTimeout(function () { mobileBackdrop.hidden = true; }, BACKDROP_TRANSITION_MS);
            }
            syncInert();
            if (returnFocus) mobileToggle.focus();
        }

        mobileToggle.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (isDrawerOpen()) {
                closeDrawer({ returnFocus: false });
            } else {
                openDrawer();
            }
        });

        if (mobileClose) {
            mobileClose.addEventListener('click', function (e) {
                e.preventDefault();
                closeDrawer();
            });
        }

        if (mobileBackdrop) {
            mobileBackdrop.addEventListener('click', function () {
                closeDrawer();
            });
        }

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isDrawerOpen()) {
                closeDrawer();
            }
        });

        // Trap Tab focus inside the open drawer
        mobileMenu.addEventListener('keydown', function (e) {
            if (e.key !== 'Tab' || !isDrawerOpen()) return;
            const focusable = Array.from(getFocusable());
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        });

        // Keep drawer/inert state clean across resizes (desktop <-> mobile)
        window.addEventListener('resize', function () {
            if (!isMobile() && isDrawerOpen()) {
                closeDrawer({ returnFocus: false });
            } else {
                syncInert();
            }
        });

        syncInert();
    }
});
