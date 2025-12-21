import { test, expect } from '@playwright/test';
import { getBaseUrl, getTestDatabases } from '../config/urls';
import { HomePage } from '../logic/pom/homePage';
import BrowserWrapper from '../infra/ui/browserWrapper';
import ApiCalls from '../logic/api/apiCalls';

// Database connection tests - uses authenticated storageState from auth.setup
test.describe('Database Connection Tests', () => {
  
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
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();
    const { postgres: postgresUrl } = getTestDatabases();

    // Connect via API - response is streaming
    const response = await apiCall.connectDatabase(postgresUrl);
    const messages = await apiCall.parseStreamingResponse(response);

    // Verify final message indicates success
    const finalMessage = messages[messages.length - 1];
    expect(finalMessage.type).toBe('final_result');
    expect(finalMessage.success).toBeTruthy();

    // Get the list of databases to find the connected database
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);

    // Find the testdb database (not testdb_delete) - could be 'testdb' or 'userId_testdb'
    const graphId = graphsList.find(id => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection();
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
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();
    const { mysql: mysqlUrl } = getTestDatabases();

    // Connect via API - response is streaming
    const response = await apiCall.connectDatabase(mysqlUrl);
    const messages = await apiCall.parseStreamingResponse(response);

    // Verify final message indicates success
    const finalMessage = messages[messages.length - 1];
    expect(finalMessage.type).toBe('final_result');
    expect(finalMessage.success).toBeTruthy();

    // Get the list of databases to find the connected database
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);

    // Find the testdb database (not testdb_delete) - could be 'testdb' or 'userId_testdb'
    const graphId = graphsList.find(id => id === 'testdb' || id.endsWith('_testdb'));
    expect(graphId).toBeTruthy();

    // Wait for UI to reflect the connection (schema loading completes)
    const connectionEstablished = await homePage.waitForDatabaseConnection();
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
    const connectionEstablished = await homePage.waitForDatabaseConnection();
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - get the list of databases
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);

    // Get the connected database ID
    const graphId = graphsList[0];
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('connect MySQL via UI (URL) -> verify via API', async () => {
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
    const connectionEstablished = await homePage.waitForDatabaseConnection();
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - get the list of databases
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);

    // Get the connected database ID
    const graphId = graphsList[0];
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('connect PostgreSQL via UI (Manual Entry) -> verify via API', async () => {
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
    const connectionEstablished = await homePage.waitForDatabaseConnection();
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - get the list of databases
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);

    // Get the connected database ID
    const graphId = graphsList[0];
    expect(graphId).toBeTruthy();

    // Verify connection appears in UI
    const isConnected = await homePage.isDatabaseConnected();
    expect(isConnected).toBeTruthy();
  });

  test('connect MySQL via UI (Manual Entry) -> verify via API', async () => {
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
    const connectionEstablished = await homePage.waitForDatabaseConnection();
    expect(connectionEstablished).toBeTruthy();

    // Verify via API - get the list of databases
    const graphsList = await apiCall.getGraphs();
    expect(graphsList).toBeDefined();
    expect(Array.isArray(graphsList)).toBeTruthy();
    expect(graphsList.length).toBeGreaterThan(0);

    // Get the connected database ID
    const graphId = graphsList[0];
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
      // Use the separate postgres delete container on port 5433
      const postgresDeleteUrl = 'postgresql://postgres:postgres@localhost:5433/testdb_delete';

      // Connect database via API
      const connectResponse = await apiCall.connectDatabase(postgresDeleteUrl);
      const connectMessages = await apiCall.parseStreamingResponse(connectResponse);
      const finalMessage = connectMessages[connectMessages.length - 1];
      expect(finalMessage.type).toBe('final_result');
      expect(finalMessage.success).toBeTruthy();

      // Wait a bit for the connection to be fully registered
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Get the graph ID from the API
      let graphsList = await apiCall.getGraphs();
      expect(graphsList.length).toBeGreaterThan(0);
      
      // Find the graph that contains 'testdb_delete' (could be 'testdb_delete' or 'userId_testdb_delete')
      const graphId = graphsList.find(id => id.includes('testdb_delete'));
      
      // If not found, log all graphs for debugging
      if (!graphId) {
        console.log('Available graphs:', graphsList);
        console.log('Looking for graph containing: testdb_delete');
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
      
      // Wait for deletion to complete
      await homePage.wait(1000);

      // Verify removed from API
      graphsList = await apiCall.getGraphs();
      expect(graphsList.length).toBe(initialCount - 1);
      expect(graphsList).not.toContain(graphId);
  });

  test('delete MySQL database via UI -> verify removed via API', async () => {  
    // Use the separate mysql delete container on port 3307
    const mysqlDeleteUrl = 'mysql://root:password@localhost:3307/testdb_delete';

    // Connect database via API
    const connectResponse = await apiCall.connectDatabase(mysqlDeleteUrl);
    const connectMessages = await apiCall.parseStreamingResponse(connectResponse);
    const finalMessage = connectMessages[connectMessages.length - 1];
    expect(finalMessage.type).toBe('final_result');
    expect(finalMessage.success).toBeTruthy();

    // Wait a bit for the connection to be fully registered
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Get the graph ID from the API - find the graph containing testdb_delete
    let graphsList = await apiCall.getGraphs();
    expect(graphsList.length).toBeGreaterThan(0);
    const graphId = graphsList.find(id => id.includes('testdb_delete'));
    
    // If not found, log all graphs for debugging
    if (!graphId) {
      console.log('Available graphs:', graphsList);
      console.log('Looking for graph containing: testdb_delete');
    }
    
    expect(graphId).toBeTruthy();
    const initialCount = graphsList.length;

    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Wait for UI to reflect the connection (increased timeout for schema loading)
    const connectionEstablished = await homePage.waitForDatabaseConnection(60000);
    expect(connectionEstablished).toBeTruthy();

    // Delete via UI - open dropdown, click delete, confirm
    await homePage.clickOnDatabaseSelector();
    await homePage.clickOnDeleteGraph(graphId!);
    await homePage.clickOnDeleteModalConfirm();
    
    // Wait for deletion to complete
    await homePage.wait(1000);

    // Verify removed from API
    graphsList = await apiCall.getGraphs();
    expect(graphsList.length).toBe(initialCount - 1);
    expect(graphsList).not.toContain(graphId);
    });
  });
});
