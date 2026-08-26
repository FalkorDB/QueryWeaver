import { test, expect } from '@playwright/test';
import { getBaseUrl } from '../config/urls';
import { Sidebar } from '../logic/pom/sidebar';
import BrowserWrapper from '../infra/ui/browserWrapper';

// Sidebar tests - uses authenticated storageState from auth.setup
test.describe('Left Sidebar Tests', () => {
  let browser: BrowserWrapper;

  test.beforeEach(async () => {
    browser = new BrowserWrapper();
  });

  test.afterEach(async () => {
    await browser.closeBrowser();
  });

  test('theme toggle changes theme between light and dark', async () => {
    const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
    await browser.setPageToFullScreen();

    const initialTheme = await sidebar.getCurrentTheme();
    expect(initialTheme).toBe('dark');
    await sidebar.clickOnThemeToggle();

    const afterToggleTheme = await sidebar.getCurrentTheme();
    expect(afterToggleTheme).toBe('light');

    await sidebar.clickOnThemeToggle();

    const finalTheme = await sidebar.getCurrentTheme();
    expect(finalTheme).toBe('dark');
  });

  test('documentation link points to correct URL', async () => {
    const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
    await browser.setPageToFullScreen();

    const docHref = await sidebar.getDocumentationLinkHref();
    expect(docHref).toBe('https://docs.falkordb.com/');
  });

  test('support link points to correct URL', async () => {
    const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
    await browser.setPageToFullScreen();

    const supportHref = await sidebar.getSupportLinkHref();
    expect(supportHref).toBe('https://discord.com/invite/jyUgBweNQz');
  });

  test('schema button opens and closes schema panel', async () => {
    const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
    await browser.setPageToFullScreen();

    const isInitiallyClosed = await sidebar.isSchemaPanelVisible();
    expect(isInitiallyClosed).toBeFalsy();
    await sidebar.clickOnSchemaButton();

    const isOpen = await sidebar.isSchemaPanelVisible();
    expect(isOpen).toBeTruthy();

    await sidebar.clickOnSchemaButton();

    const isClosedAgain = await sidebar.isSchemaPanelVisible();
    expect(isClosedAgain).toBeFalsy();
  });

  // Routing tests: verify react-router (v8) navigation still works after the
  // react-router-dom -> react-router migration.
  test('settings button navigates to /settings and back navigates home', async () => {
    const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
    await browser.setPageToFullScreen();

    await sidebar.clickOnSettingsButton();
    await sidebar.waitForUrl('**/settings');
    expect(sidebar.getCurrentURL()).toContain('/settings');

    await sidebar.refreshPage();
    expect(sidebar.getCurrentURL()).toContain('/settings');
  });

  test('unknown route renders the not-found page', async () => {
    const sidebar = await browser.createNewPage(Sidebar, `${getBaseUrl()}/this-route-does-not-exist`);
    await browser.setPageToFullScreen();

    await sidebar.waitForUrl('**/this-route-does-not-exist');
    const bodyText = await sidebar.getPageContent();
    expect(bodyText).toContain('404');
    expect(bodyText).toContain('Oops! Page not found');
  });

  // Issue #239: a SidebarIcon with neither an onClick nor an href used to fall
  // back to a `<Link to="#">`, rendering a button that looks live but is inert.
  test('sidebar contains no inert placeholder links', async () => {
    const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
    await browser.setPageToFullScreen();

    await expect(sidebar.sidebarDeadLinks).toHaveCount(0);
  });

  // Issue #179: the schema panel is resizable, defaults to 50% of the viewport
  // and clamps to 20%..60% rather than freezing when the drag overshoots.
  test.describe('Schema panel sizing', () => {
    test('opens at half the viewport width', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await browser.setPageToFullScreen();

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelLocator).toBeVisible();

      const viewportWidth = await sidebar.getViewportWidth();
      // The panel animates open, so poll until the width settles. The slack
      // absorbs the rounding from the floor() in clampPanelWidth.
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - viewportWidth * 0.5))
        .toBeLessThanOrEqual(2);
    });

    test('clamps to the minimum when the drag overshoots', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await browser.setPageToFullScreen();

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelResizeHandle).toBeVisible();

      const viewportWidth = await sidebar.getViewportWidth();
      // Drag well past the 20% minimum; the panel should pin, not freeze.
      await sidebar.dragSchemaPanelResizeHandleTo(1);

      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - viewportWidth * 0.2))
        .toBeLessThanOrEqual(2);
    });

    test('clamps to the maximum when the drag overshoots', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await browser.setPageToFullScreen();

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelResizeHandle).toBeVisible();

      const viewportWidth = await sidebar.getViewportWidth();
      await sidebar.dragSchemaPanelResizeHandleTo(viewportWidth - 1);

      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - viewportWidth * 0.6))
        .toBeLessThanOrEqual(2);
    });

    // The handle is a focusable role="separator", so a pointer must not be the
    // only way to size the panel. This also guards the ARIA values: a handle
    // that reports a width it did not apply is worse than no handle at all.
    test('resizes with the keyboard and keeps aria-valuenow in step', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await browser.setPageToFullScreen();

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelResizeHandle).toBeVisible();

      const viewportWidth = await sidebar.getViewportWidth();
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - viewportWidth * 0.5))
        .toBeLessThanOrEqual(2);

      // ArrowLeft moves in 24px steps.
      const before = await sidebar.getSchemaPanelWidth();
      await sidebar.pressSchemaPanelResizeKey('ArrowLeft', 2);
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - (before - 48)))
        .toBeLessThanOrEqual(2);

      // Home and End jump to the same 20%/60% bounds the drag clamps to.
      await sidebar.pressSchemaPanelResizeKey('Home');
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - viewportWidth * 0.2))
        .toBeLessThanOrEqual(2);

      await sidebar.pressSchemaPanelResizeKey('End');
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - viewportWidth * 0.6))
        .toBeLessThanOrEqual(2);

      // The announced value must match what the panel actually renders.
      const width = await sidebar.getSchemaPanelWidth();
      expect(Math.abs((await sidebar.getSchemaPanelAriaValueNow()) - width)).toBeLessThanOrEqual(2);
    });

    // The bounds are viewport-relative, so re-clamping the *current* width on
    // every window resize threw the user's choice away: narrowing pinned it to
    // the minimum and widening never brought it back.
    test('restores the chosen width after a transient narrowing', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await browser.setPageToFullScreen();

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelResizeHandle).toBeVisible();

      // Widest the panel goes at 1920px: 60% == 1152px.
      await sidebar.pressSchemaPanelResizeKey('End');
      await expect.poll(async () => await sidebar.getSchemaPanelWidth()).toBeGreaterThan(1100);

      // Dock devtools / tile the window: the panel has to clamp down to the
      // new 60% maximum... (staying above the 768px mobile breakpoint, below
      // which the panel is sized by a CSS class and ignores `width`).
      await sidebar.setViewportWidth(1000);
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - 1000 * 0.6))
        .toBeLessThanOrEqual(2);

      // ...and come back to the chosen width once there is room again.
      await sidebar.setViewportWidth(1920);
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - 1920 * 0.6))
        .toBeLessThanOrEqual(2);
    });

    // The "recompute 50% of the current viewport on open" fix for issue #179
    // is skipped once the user picks a width. Focusing the separator with a
    // click is not picking a width.
    test('a bare click on the handle does not count as a resize', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await browser.setPageToFullScreen();

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelResizeHandle).toBeVisible();
      await sidebar.clickSchemaPanelResizeHandle();

      // Close, resize the window, reopen: the panel must still track 50%.
      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelLocator).toBeHidden();
      await sidebar.setViewportWidth(1200);
      await sidebar.clickOnSchemaButton();

      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - 1200 * 0.5))
        .toBeLessThanOrEqual(2);
    });

    // 20% of a small desktop window is ~150-200px, where the heading wraps and
    // the canvas controls stack into three rows. A pixel floor keeps the panel
    // usable; the 60% maximum still wins over it.
    test('keeps a usable minimum width on a narrow desktop window', async () => {
      const sidebar = await browser.createNewPage(Sidebar, getBaseUrl());
      await sidebar.setViewportWidth(900);

      await sidebar.clickOnSchemaButton();
      await expect(sidebar.schemaPanelResizeHandle).toBeVisible();

      await sidebar.pressSchemaPanelResizeKey('Home');
      await expect
        .poll(async () => Math.abs((await sidebar.getSchemaPanelWidth()) - 300))
        .toBeLessThanOrEqual(2);
    });
  });

  // Issue #238: the mobile burger used to be rendered twice with the same
  // test id, and the in-sidebar copy stayed mounted (off-screen) after closing,
  // so the icon appeared not to respond.
  test.describe('Mobile sidebar toggle', () => {
    test('is unique and toggles the sidebar open and closed', async () => {
      // The viewport has to be narrow before the app mounts, so that the
      // 768px breakpoint puts the sidebar in its collapsed starting state.
      const sidebar = await browser.createNewPage(Sidebar);
      await browser.setPageToMobileViewport();
      await browser.navigateTo(getBaseUrl());

      const toggle = sidebar.sidebarToggle;
      // Exactly one toggle in the DOM — the duplicate test id previously made
      // any getByTestId('sidebar-toggle') call a strict-mode violation.
      await expect(toggle).toHaveCount(1);
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');

      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      await expect(toggle).toHaveCount(1);

      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await expect(toggle).toHaveCount(1);
    });
  });
});
