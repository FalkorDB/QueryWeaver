import { test, expect } from '@playwright/test';
import { getBaseUrl, getTestDatabases } from '../config/urls';
import { HomePage } from '../logic/pom/homePage';
import BrowserWrapper from '../infra/ui/browserWrapper';
import ApiCalls from '../logic/api/apiCalls';

// Chat feature tests - uses authenticated storageState from auth.setup
test.describe('Chat Feature Tests', () => {
  let browser: BrowserWrapper;
  let apiCall: ApiCalls;

  // Set longer timeout for chat tests (60 seconds)
  test.setTimeout(60000);

  test.beforeEach(async () => {
    browser = new BrowserWrapper();
    apiCall = new ApiCalls();
  });

  test.afterEach(async () => {
    await browser.closeBrowser();
  });

  test('chat controls disabled without database connection', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl(), 'e2e/.auth/user2.json');
    await browser.setPageToFullScreen();

    // Try to send query without database connection
    await homePage.sendQuery("Show me all users");

    // Wait for toast to appear
    const toastAppeared = await homePage.waitForToast(5000);
    expect(toastAppeared).toBeTruthy();

    // Verify toast title
    const hasCorrectTitle = await homePage.verifyToastTitle("No Database Available");
    expect(hasCorrectTitle).toBeTruthy();

    // Verify toast description
    const hasCorrectDescription = await homePage.verifyToastDescription("Please upload a database schema first");
    expect(hasCorrectDescription).toBeTruthy();
  });

  test('valid query shows SQL, results, and AI response', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected (will skip if already connected)
    await homePage.ensureDatabaseConnected(apiCall);
    // Send query
    await homePage.sendQuery("Show me one users");

    // Wait for processing to complete
    const processingComplete = await homePage.waitForProcessingToComplete();
    expect(processingComplete).toBeTruthy();

    // Verify SQL query message
    const sqlVisible = await homePage.isSQLQueryMessageVisible();
    expect(sqlVisible).toBeTruthy();

    const hasSQLContent = await homePage.verifySQLQueryContains("SELECT");
    expect(hasSQLContent).toBeTruthy();

    // Verify results table
    const resultsVisible = await homePage.isQueryResultsMessageVisible();
    expect(resultsVisible).toBeTruthy();

    const rowCount = await homePage.getResultsTableRowCount();
    expect(rowCount).toBe(1);

    // Verify AI response (should have at least 2: welcome + final response)
    const finalAIMessageCount = await homePage.getAIMessageCount();
    expect(finalAIMessageCount).toBeGreaterThanOrEqual(2); // At least welcome + final response
  });

  test('off-topic query shows AI message without SQL or results', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected (will skip if already connected)
    await homePage.ensureDatabaseConnected(apiCall);

    // Send off-topic query
    await homePage.sendQuery("hello");

    // Wait for processing to complete
    const processingComplete = await homePage.waitForProcessingToComplete();
    expect(processingComplete).toBeTruthy();

    // Verify Query Analysis message appears (but without actual SQL)
    const sqlMessageVisible = await homePage.isSQLQueryMessageVisible();
    expect(sqlMessageVisible).toBeTruthy();

    // Verify NO actual SQL content (should say "Query Analysis" or "Off topic")
    const hasSQLContent = await homePage.verifySQLQueryContains("SELECT");
    expect(hasSQLContent).toBeFalsy();

    // Verify NO results table
    const resultsVisible = await homePage.isQueryResultsMessageVisible();
    expect(resultsVisible).toBeFalsy();

    // Verify AI response has content explaining it's off-topic
    const aiText = await homePage.getLastAIMessageText();
    expect(aiText.length).toBeGreaterThan(0);
  });

  test('multiple sequential queries maintain conversation history', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected (will skip if already connected)
    await homePage.ensureDatabaseConnected(apiCall);

    // Get initial message count (should be 1 - welcome message)
    const initialCount = await homePage.getMessageCount();
    expect(initialCount).toBeGreaterThan(0);

    // Send first query
    await homePage.sendQuery("Show me all products");
    await homePage.waitForProcessingToComplete();
    const firstResponseComplete = await homePage.waitForCompleteQueryResponse();
    expect(firstResponseComplete).toBeTruthy();

    // Get message count after first query
    const afterFirstQuery = await homePage.getMessageCount();
    expect(afterFirstQuery).toBeGreaterThan(initialCount);

    // Send second query
    await homePage.sendQuery("How many orders are there?");
    await homePage.waitForProcessingToComplete();
    const secondResponseComplete = await homePage.waitForCompleteQueryResponse();
    expect(secondResponseComplete).toBeTruthy();

    // Get final message count
    const finalCount = await homePage.getMessageCount();
    expect(finalCount).toBeGreaterThan(afterFirstQuery);

    // Verify both queries have results
    const resultsVisible = await homePage.isQueryResultsMessageVisible();
    expect(resultsVisible).toBeTruthy();
  });

  test('empty query submission is prevented', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected (will skip if already connected)
    await homePage.ensureDatabaseConnected(apiCall);

    // Verify send button is disabled with empty input
    const isSendButtonDisabled = await homePage.isSendQueryButtonDisabled();
    expect(isSendButtonDisabled).toBeTruthy();
  });

  test('rapid query submission is prevented during processing', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected (will skip if already connected)
    await homePage.ensureDatabaseConnected(apiCall);

    // Send first query
    await homePage.sendQuery("Show me all users");

    const isTextareaDisabled = await homePage.isQueryTextareaDisabled();
    const isSendButtonDisabled = await homePage.isSendQueryButtonDisabled();

    // At least one should be disabled during processing
    const isDisabledDuringProcessing = isTextareaDisabled || isSendButtonDisabled;
    expect(isDisabledDuringProcessing).toBeTruthy();
  });

  test('switching databases clears chat history', async () => {
    // Connect two databases via API
    const { postgres: postgresUrl } = getTestDatabases();

    // Connect first database (testdb on port 5432) - response is streaming
    const response1 = await apiCall.connectDatabase(postgresUrl);
    const messages1 = await apiCall.parseStreamingResponse(response1);
    const finalMessage1 = messages1[messages1.length - 1];
    expect(finalMessage1.type).toBe('final_result');
    expect(finalMessage1.success).toBeTruthy();

    // Connect second database (testdb_delete on port 5433) - response is streaming
    // Need to change both the database name AND the port
    const secondDbUrl = 'postgresql://postgres:postgres@localhost:5433/testdb_delete';
    const response2 = await apiCall.connectDatabase(secondDbUrl);
    const messages2 = await apiCall.parseStreamingResponse(response2);
    const finalMessage2 = messages2[messages2.length - 1];
    expect(finalMessage2.type).toBe('final_result');
    expect(finalMessage2.success).toBeTruthy();

    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Wait for page to load databases
    await homePage.wait(2000);

    // Get initial message count (should be 1 - welcome message)
    const initialCount = await homePage.getMessageCount();
    expect(initialCount).toBe(1);

    // Send query to first database (testdb should be selected by default)
    await homePage.sendQuery("Show me one users");
    await homePage.waitForProcessingToComplete();

    // Get message count after query (should be more than initial)
    const afterQueryCount = await homePage.getMessageCount();
    expect(afterQueryCount).toBeGreaterThan(initialCount);

    // Switch to second database (testdb_delete)
    await homePage.selectDatabase("testdb_delete");

    // Wait a moment for chat to clear
    await homePage.wait(1000);

    // Verify chat is cleared (only welcome message remains)
    const afterSwitchCount = await homePage.getMessageCount();
    expect(afterSwitchCount).toBe(1);

    // Verify only AI welcome message is present
    const aiMessageCount = await homePage.getAIMessageCount();
    expect(aiMessageCount).toBe(1);
  });

  test('destructive operation shows inline confirmation and executes on confirm', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected
    await homePage.ensureDatabaseConnected(apiCall);

    // Generate random username and email to avoid conflicts
    const randomUsername = `testuser${Date.now()}`;
    const randomEmail = `${randomUsername}@test.com`;

    // Send INSERT query
    await homePage.sendQuery(`add one user "${randomUsername}" with email "${randomEmail}"`);

    // Wait for confirmation message to appear (increased timeout for slow CI)
    const confirmationAppeared = await homePage.waitForConfirmationMessage(30000);
    expect(confirmationAppeared).toBeTruthy();

    // Verify confirmation message is visible
    const confirmationVisible = await homePage.isConfirmationMessageVisible();
    expect(confirmationVisible).toBeTruthy();

    // Verify confirmation contains INSERT operation type
    const hasInsertText = await homePage.verifyConfirmationContains('INSERT');
    expect(hasInsertText).toBeTruthy();

    // Click confirm button
    await homePage.clickConfirmButton();

    // Wait for operation to complete
    const processingComplete = await homePage.waitForProcessingToComplete();
    expect(processingComplete).toBeTruthy();

    // Verify confirmation message is no longer visible
    const confirmationStillVisible = await homePage.isConfirmationMessageVisible();
    expect(confirmationStillVisible).toBeFalsy();

    // Verify AI response appears after confirmation
    const finalAIMessageCount = await homePage.getAIMessageCount();
    expect(finalAIMessageCount).toBeGreaterThan(1); // Welcome message + execution result
  });

  test('duplicate record shows user-friendly error message', async () => {
    const homePage = await browser.createNewPage(HomePage, getBaseUrl());
    await browser.setPageToFullScreen();

    // Ensure database is connected
    await homePage.ensureDatabaseConnected(apiCall);
    const randomUsername = `testuser${Date.now()}`;
    const randomEmail = `${randomUsername}@test.com`;

    // First insertion - should succeed
    await homePage.sendQuery(`add one user "${randomUsername}" with email "${randomEmail}"`);
    const confirmationAppeared1 = await homePage.waitForConfirmationMessage(30000);
    expect(confirmationAppeared1).toBeTruthy();
    await homePage.clickConfirmButton();
    await homePage.waitForProcessingToComplete();

    // Second insertion attempt - should fail with duplicate error
    await homePage.sendQuery(`add one user "${randomUsername}" with email "${randomEmail}"`);
    const confirmationAppeared2 = await homePage.waitForConfirmationMessage(30000);
    expect(confirmationAppeared2).toBeTruthy();
    await homePage.clickConfirmButton();
    await homePage.waitForProcessingToComplete();

    // Verify error message indicates a duplicate/conflict occurred
    const lastAIMessage = await homePage.getLastAIMessageText();
    const hasErrorIndicator = lastAIMessage.toLowerCase().includes('already exists');
    expect(hasErrorIndicator).toBeTruthy();
  });
});
