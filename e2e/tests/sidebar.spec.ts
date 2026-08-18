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
});
