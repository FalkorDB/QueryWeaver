import { test, expect } from '@playwright/test';
import { getBaseUrl, getTestDatabases } from '../config/urls';
import { HomePage } from '../logic/pom/homePage';
import BrowserWrapper from '../infra/ui/browserWrapper';
import ApiCalls from '../logic/api/apiCalls';

// Database connection tests - uses authenticated storageState from auth.setup
test.describe.serial('Database Connection Tests', () => {
  
  let browser: BrowserWrapper;
  let apiCall: ApiCalls;

  test.beforeEach(async () => {
    browser = new BrowserWrapper();
    apiCall = new ApiCalls();
  });

  test.afterEach(async () => {
    await browser.closeBrowser();
  });

  test('connect PostgreSQL via API -> verify in UI', async () => {
    test.setTimeout(120000); // Allow extra time for schema loading in CI
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();
    const { postgres: postgresUrl } = getTestDatabases();

    // Connect via API - response is streaming (retry on transient errors)
    const messages = await apiCall.connectDatabaseWithRetry(postgresUrl);

    // Verify final message indicates success
    expect(messages.length).toBeGreaterThan(0);
    const finalMessage = messages[messages.length - 1];
    if (finalMessage.type !== 'final_result') {
      console.log(`[PostgreSQL API connect] unexpected final message: ${JSON.stringify(finalMessage)}`);
    }
    expect(finalMessage.type).toBe('final_result');
    expect(finalMessage.success).toBeTruthy();

    // Get the list of databases to find the connected database
    const graphsList = await apiCall.waitForGraphs(
      (graphs) => graphs.some((id) => id === 'testdb' || id.endsWith('_testdb')),
      30000
    );
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);
    console.log(`[PostgreSQL API connect] graphs after connection: ${JSON.stringify(graphsList)}`);

    // Find the testdb database (not testdb_delete) - could be 'testdb' or 'userId_testdb'
    const graphId = graphsList.find(id => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
    expect(connectionEstablished).toBeTruthy();

    // Verify connection appears in UI - check database status badge
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();

    // Verify the selected database name matches the graph ID
    const selectedDatabaseName = await homePage.getSelectedDatabaseName();
    expect(selectedDatabaseName).toBe(graphId);

    // Open database selector dropdown to verify the specific database appears in the list
    await homePage.clickOnDatabaseSelector();

    // Verify the specific database option is visible in the dropdown
    const isDatabaseVisible = await homePage.isDatabaseInList(graphId!);
    expect(isDatabaseVisible).toBeTruthy();
  });

  test('connect MySQL via API -> verify in UI', async () => {
    test.setTimeout(120000); // Allow extra time for schema loading in CI
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();
    const { mysql: mysqlUrl } = getTestDatabases();

    // Connect via API - response is streaming (retry on transient errors)
    const messages = await apiCall.connectDatabaseWithRetry(mysqlUrl);

    // Verify final message indicates success
    expect(messages.length).toBeGreaterThan(0);
    const finalMessage = messages[messages.length - 1];
    if (finalMessage.type !== 'final_result') {
      console.log(`[MySQL API connect] unexpected final message: ${JSON.stringify(finalMessage)}`);
    }
    expect(finalMessage.type).toBe('final_result');
    expect(finalMessage.success).toBeTruthy();

    // Get the list of databases to find the connected database
    const graphsList = await apiCall.waitForGraphs(
      (graphs) => graphs.some((id) => id === 'testdb' || id.endsWith('_testdb')),
      30000
    );
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);
    console.log(`[MySQL API connect] graphs after connection: ${JSON.stringify(graphsList)}`);

    // Find the testdb database (not testdb_delete) - could be 'testdb' or 'userId_testdb'
    const graphId = graphsList.find(id => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
    expect(connectionEstablished).toBeTruthy();

    // Verify connection appears in UI - check database status badge
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();

    // Verify the selected database name matches the graph ID
    const selectedDatabaseName = await homePage.getSelectedDatabaseName();
    expect(selectedDatabaseName).toBe(graphId);

    // Open database selector dropdown to verify the specific database appears in the list
    await homePage.clickOnDatabaseSelector();

    // Verify the specific database option is visible in the dropdown
    const isDatabaseVisible = await homePage.isDatabaseInList(graphId!);
    expect(isDatabaseVisible).toBeTruthy();
  });

  test('connect PostgreSQL via UI (URL) -> verify via API', async () => {
    test.setTimeout(120000); // Allow extra time for schema loading in CI
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();
    const { postgres: postgresUrl } = getTestDatabases();

    // Connect via UI using URL mode
    await homePage.clickOnConnectDatabase();
    await homePage.selectDatabaseType('postgresql');
    await homePage.selectConnectionModeUrl();
    await homePage.enterConnectionUrl(postgresUrl);
    await homePage.clickOnDatabaseModalConnect();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
    if (!connectionEstablished) {
      console.log('[PostgreSQL URL connect] waitForDatabaseConnection timed out');
    }
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - poll until the expected testdb graph appears
    const graphsList = await apiCall.waitForGraphs(
      (graphs) => graphs.some((id) => id === 'testdb' || id.endsWith('_testdb')),
      30000
    );
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);
    console.log(`[PostgreSQL URL connect] graphs after connection: ${JSON.stringify(graphsList)}`);

    // Get the connected database ID
    const graphId = graphsList.find((id) => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('connect MySQL via UI (URL) -> verify via API', async () => {
    test.setTimeout(120000); // Allow extra time for schema loading in CI
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();
    const { mysql: mysqlUrl } = getTestDatabases();

    // Connect via UI using URL mode
    await homePage.clickOnConnectDatabase();
    await homePage.selectDatabaseType('mysql');
    await homePage.selectConnectionModeUrl();
    await homePage.enterConnectionUrl(mysqlUrl);
    await homePage.clickOnDatabaseModalConnect();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
    if (!connectionEstablished) {
      console.log('[MySQL URL connect] waitForDatabaseConnection timed out');
    }
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - poll until the expected testdb graph appears
    const graphsList = await apiCall.waitForGraphs(
      (graphs) => graphs.some((id) => id === 'testdb' || id.endsWith('_testdb')),
      30000
    );
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);
    console.log(`[MySQL URL connect] graphs after connection: ${JSON.stringify(graphsList)}`);

    // Get the connected database ID
    const graphId = graphsList.find((id) => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('connect PostgreSQL via UI (Manual Entry) -> verify via API', async () => {
    test.setTimeout(120000); // Allow extra time for schema loading in CI
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Connect via UI using manual entry mode
    await homePage.clickOnConnectDatabase();
    await homePage.selectDatabaseType('postgresql');
    await homePage.selectConnectionModeManual();
    await homePage.enterConnectionDetails(
      'localhost',
      '5432',
      'testdb',
      'postgres',
      'postgres'
    );
    await homePage.clickOnDatabaseModalConnect();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
    if (!connectionEstablished) {
      console.log('[PostgreSQL Manual connect] waitForDatabaseConnection timed out');
    }
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - poll until the expected testdb graph appears
    const graphsList = await apiCall.waitForGraphs(
      (graphs) => graphs.some((id) => id === 'testdb' || id.endsWith('_testdb')),
      30000
    );
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);
    console.log(`[PostgreSQL Manual connect] graphs after connection: ${JSON.stringify(graphsList)}`);

    // Get the connected database ID
    const graphId = graphsList.find((id) => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('connect MySQL via UI (Manual Entry) -> verify via API', async () => {
    test.setTimeout(120000); // Allow extra time for schema loading in CI
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Connect via UI using manual entry mode
    await homePage.clickOnConnectDatabase();
    await homePage.selectDatabaseType('mysql');
    await homePage.selectConnectionModeManual();
    await homePage.enterConnectionDetails(
      'localhost',
      '3306',
      'testdb',
      'root',
      'password'
    );
    await homePage.clickOnDatabaseModalConnect();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
    if (!connectionEstablished) {
      console.log('[MySQL Manual connect] waitForDatabaseConnection timed out');
    }
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - poll until the expected testdb graph appears
    const graphsList = await apiCall.waitForGraphs(
      (graphs) => graphs.some((id) => id === 'testdb' || id.endsWith('_testdb')),
      30000
    );
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);
    console.log(`[MySQL Manual connect] graphs after connection: ${JSON.stringify(graphsList)}`);

    // Get the connected database ID
    const graphId = graphsList.find((id) => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('invalid connection string -> shows error', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    const invalidUrl = 'invalid://connection:string';

    // Attempt connection via UI
    await homePage.clickOnConnectDatabase();

    // Select database type (PostgreSQL)
    await homePage.selectDatabaseType('postgresql');

    // Select URL connection mode
    await homePage.selectConnectionModeUrl();

    // Enter invalid connection URL
    await homePage.enterConnectionUrl(invalidUrl);

    // Click connect button
    await homePage.clickOnDatabaseModalConnect();

    // Verify the invalid database does not appear in the dropdown
    // Get the list of databases to verify nothing was connected
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).not.toContain(invalidUrl);
  });

  // Delete tests run serially to avoid conflicts
  test.describe.serial('Database Deletion Tests', () => {
    test('delete PostgreSQL database via UI -> verify removed via API', async () => {
      test.setTimeout(180000); // Allow extra time: schema loading + UI interaction
      // Use the separate postgres delete container on port 5433
      const postgresDeleteUrl = 'postgresql://postgres:postgres@localhost:5433/testdb_delete';

      // Connect database via API (retry on transient errors)
      const connectMessages = await apiCall.connectDatabaseWithRetry(postgresDeleteUrl);
      expect(connectMessages.length).toBeGreaterThan(0);
      const finalMessage = connectMessages[connectMessages.length - 1];
      if (finalMessage.type !== 'final_result') {
        console.log(`[PostgreSQL delete connect] unexpected final message: ${JSON.stringify(finalMessage)}`);
      }
      expect(finalMessage.type).toBe('final_result');
      expect(finalMessage.success).toBeTruthy();

      // Poll until the graph appears in the API
      let graphsList = await apiCall.waitForGraphs(
        (graphs) => graphs.some((id) => id === 'testdb_delete' || id.endsWith('_testdb_delete')),
        30000
      );
      expect(graphsList.length).toBeGreaterThan(0);
      
      // Find the graph that is 'testdb_delete' or '{userId}_testdb_delete'
      const graphId = graphsList.find(id => id === 'testdb_delete' || id.endsWith('_testdb_delete'));
      
      if (!graphId) {
        console.log('[PostgreSQL delete] Available graphs:', graphsList);
        console.log('[PostgreSQL delete] Looking for graph containing: testdb_delete');
      }
      
      expect(graphId).toBeTruthy();
      const initialCount = graphsList.length;

      // Create new page and open it
      const homePage = await browser.createNewPage(HomePage, getBaseUrl());
      await browser.setPageToFullScreen();

      // Delete via UI - open dropdown, click delete, confirm
      await homePage.clickOnDatabaseSelector();
      await homePage.clickOnDeleteGraph(graphId!);
      await homePage.clickOnDeleteModalConfirm();
      
      // Wait for deletion to complete - poll until graphId is absent (up to 30s)
      graphsList = await apiCall.waitForGraphs(
        (graphs) => !graphs.some((id) => id === graphId),
        30000
      );
      expect(graphsList.length).toBe(initialCount - 1);
      expect(graphsList).not.toContain(graphId);
    });

    test('delete MySQL database via UI -> verify removed via API', async () => {
      test.setTimeout(180000); // Allow extra time: schema loading + UI interaction
      // Use the separate mysql delete container on port 3307
      const mysqlDeleteUrl = 'mysql://root:password@localhost:3307/testdb_delete';

      // Connect database via API (retry on transient errors)
      const connectMessages = await apiCall.connectDatabaseWithRetry(mysqlDeleteUrl);
      expect(connectMessages.length).toBeGreaterThan(0);
      const finalMessage = connectMessages[connectMessages.length - 1];
      if (finalMessage.type !== 'final_result') {
        console.log(`[MySQL delete connect] unexpected final message: ${JSON.stringify(finalMessage)}`);
      }
      expect(finalMessage.type).toBe('final_result');
      expect(finalMessage.success).toBeTruthy();

      // Poll until the graph appears in the API
      let graphsList = await apiCall.waitForGraphs(
        (graphs) => graphs.some((id) => id === 'testdb_delete' || id.endsWith('_testdb_delete')),
        30000
      );
      expect(graphsList.length).toBeGreaterThan(0);
      const graphId = graphsList.find(id => id === 'testdb_delete' || id.endsWith('_testdb_delete'));
      
      if (!graphId) {
        console.log('[MySQL delete] Available graphs:', graphsList);
        console.log('[MySQL delete] Looking for graph containing: testdb_delete');
      }
      
      expect(graphId).toBeTruthy();
      const initialCount = graphsList.length;

      const homePage = await browser.createNewPage(HomePage, getBaseUrl());
      await browser.setPageToFullScreen();

      // Wait for UI to reflect the connection (increased timeout for schema loading)
      const connectionEstablished = await homePage.waitForDatabaseConnection(90000);
      if (!connectionEstablished) {
        console.log('[MySQL delete] waitForDatabaseConnection timed out');
      }
      expect(connectionEstablished).toBeTruthy();

      // Delete via UI - open dropdown, click delete, confirm
      await homePage.clickOnDatabaseSelector();
      await homePage.clickOnDeleteGraph(graphId!);
      await homePage.clickOnDeleteModalConfirm();
      
      // Wait for deletion to complete - poll until graphId is absent (up to 30s)
      graphsList = await apiCall.waitForGraphs(
        (graphs) => !graphs.some((id) => id === graphId),
        30000
      );
      expect(graphsList.length).toBe(initialCount - 1);
      expect(graphsList).not.toContain(graphId);
    });
  });
});
