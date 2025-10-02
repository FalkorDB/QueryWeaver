/**
 * Left toolbar behavior extracted from template script.
 * This module exports initLeftToolbar and can be imported so bundlers include it in the main bundle.
 */
export function initLeftToolbar(): void {
    const nav = document.getElementById('left-toolbar') as HTMLElement | null;
    const btn = document.getElementById('burger-toggle-btn') as HTMLElement | null;
    if (!nav || !btn) return;

    function setOpen(open: boolean) {
        // `nav` and `btn` are checked above; use non-null assertions to satisfy TypeScript
        if (open) {
            nav!.classList.remove('collapsed');
            document.body.classList.add('left-toolbar-open');
            btn!.setAttribute('title', 'Close menu');
            btn!.setAttribute('aria-label', 'Close menu');
            btn!.setAttribute('aria-pressed', 'true');
            btn!.setAttribute('aria-expanded', 'true');
        } else {
            nav!.classList.add('collapsed');
            document.body.classList.remove('left-toolbar-open');
            btn!.setAttribute('title', 'Open menu');
            btn!.setAttribute('aria-label', 'Open menu');
            btn!.setAttribute('aria-pressed', 'false');
            btn!.setAttribute('aria-expanded', 'false');
        }
    }

    const mq = window.matchMedia('(min-width: 768px)');

    try {
        setOpen(mq.matches);
    } catch {
        setOpen(true);
    }

    // Support both modern and legacy addListener APIs
    if (typeof (mq as MediaQueryList).addEventListener === 'function') {
        (mq as MediaQueryList).addEventListener('change', (ev: MediaQueryListEvent) => setOpen(ev.matches));
    } else if (typeof (mq as any).addListener === 'function') {
        (mq as any).addListener((ev: MediaQueryListEvent) => setOpen(ev.matches));
    }

    let ignoreNextClick = false;

    function handleToggleEvent() {
        const isCollapsed = nav!.classList.contains('collapsed');
        setOpen(isCollapsed);
    }

    btn.addEventListener('pointerdown', function (e: PointerEvent) {
        e.preventDefault();
        handleToggleEvent();
        ignoreNextClick = true;
    });

    btn.addEventListener('click', function () {
        if (ignoreNextClick) {
            ignoreNextClick = false;
            return;
        }
        handleToggleEvent();
    });

    // Expose a minimal API for other scripts
    (window as any).__leftToolbar = {
        open: () => setOpen(true),
        close: () => setOpen(false),
        toggle: () => setOpen(!nav.classList.contains('collapsed')),
    };
}

// Note: We don't auto-init here. Importing module and calling initLeftToolbar() from the app entry
// ensures the bundler includes this file and initialization timing stays explicit.
