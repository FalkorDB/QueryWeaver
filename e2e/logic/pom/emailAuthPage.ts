import { Locator, Page } from "@playwright/test";
import { waitForElementToBeVisible } from "../../infra/utils";
import BasePage from "../../infra/ui/basePage";

/**
 * Email Authentication Page Object Model
 * Handles all email signup and signin functionality
 */
export class EmailAuthPage extends BasePage {
  // ==================== LOCATORS ====================

  // Email Authentication Buttons
  private get emailAuthBtn(): Locator {
    return this.page.getByTestId("email-auth-btn");
  }

  // Email Signup Form Elements
  private get emailSignupForm(): Locator {
    return this.page.getByTestId("email-signup-form");
  }

  private get firstNameInput(): Locator {
    return this.page.getByTestId("firstname-input");
  }

  private get lastNameInput(): Locator {
    return this.page.getByTestId("lastname-input");
  }

  private get emailSignupInput(): Locator {
    return this.page.getByTestId("email-signup-input");
  }

  private get passwordSignupInput(): Locator {
    return this.page.getByTestId("password-signup-input");
  }

  private get confirmPasswordInput(): Locator {
    return this.page.getByTestId("confirm-password-input");
  }

  private get createAccountBtn(): Locator {
    return this.page.getByTestId("create-account-btn");
  }

  private get signupError(): Locator {
    return this.page.getByTestId("signup-error");
  }

  // Email Signin Form Elements
  private get emailSigninForm(): Locator {
    return this.page.getByTestId("email-signin-form");
  }

  private get emailSigninInput(): Locator {
    return this.page.getByTestId("email-signin-input");
  }

  private get passwordSigninInput(): Locator {
    return this.page.getByTestId("password-signin-input");
  }

  private get signinSubmitBtn(): Locator {
    return this.page.getByTestId("signin-submit-btn");
  }

  private get signinError(): Locator {
    return this.page.getByTestId("signin-error");
  }

  // Form Toggle Links
  private get switchToSignupLink(): Locator {
    return this.page.getByTestId("switch-to-signup-link");
  }

  private get switchToSigninLink(): Locator {
    return this.page.getByTestId("switch-to-signin-link");
  }

  private get switchModeLink(): Locator {
    return this.page.getByTestId("switch-mode-link");
  }

  // User Display Elements
  private get userEmailDisplay(): Locator {
    return this.page.getByTestId("user-email-display");
  }

  // ==================== INTERACTION HELPERS ====================

  // Email Authentication Button - InteractWhenVisible
  private async interactWithEmailAuthBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.emailAuthBtn);
    if (!isVisible) throw new Error("Email auth button is not visible!");
    return this.emailAuthBtn;
  }

  // Email Signup Form Elements - InteractWhenVisible
  private async interactWithEmailSignupForm(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.emailSignupForm);
    if (!isVisible) throw new Error("Email signup form is not visible!");
    return this.emailSignupForm;
  }

  private async interactWithFirstNameInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.firstNameInput);
    if (!isVisible) throw new Error("First name input is not visible!");
    return this.firstNameInput;
  }

  private async interactWithLastNameInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.lastNameInput);
    if (!isVisible) throw new Error("Last name input is not visible!");
    return this.lastNameInput;
  }

  private async interactWithEmailSignupInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.emailSignupInput);
    if (!isVisible) throw new Error("Email signup input is not visible!");
    return this.emailSignupInput;
  }

  private async interactWithPasswordSignupInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.passwordSignupInput);
    if (!isVisible) throw new Error("Password signup input is not visible!");
    return this.passwordSignupInput;
  }

  private async interactWithConfirmPasswordInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.confirmPasswordInput);
    if (!isVisible) throw new Error("Confirm password input is not visible!");
    return this.confirmPasswordInput;
  }

  private async interactWithCreateAccountBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.createAccountBtn);
    if (!isVisible) throw new Error("Create account button is not visible!");
    return this.createAccountBtn;
  }

  private async interactWithSignupError(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.signupError);
    if (!isVisible) throw new Error("Signup error is not visible!");
    return this.signupError;
  }

  // Email Signin Form Elements - InteractWhenVisible
  private async interactWithEmailSigninForm(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.emailSigninForm);
    if (!isVisible) throw new Error("Email signin form is not visible!");
    return this.emailSigninForm;
  }

  private async interactWithEmailSigninInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.emailSigninInput);
    if (!isVisible) throw new Error("Email signin input is not visible!");
    return this.emailSigninInput;
  }

  private async interactWithPasswordSigninInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.passwordSigninInput);
    if (!isVisible) throw new Error("Password signin input is not visible!");
    return this.passwordSigninInput;
  }

  private async interactWithSigninSubmitBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.signinSubmitBtn);
    if (!isVisible) throw new Error("Signin submit button is not visible!");
    return this.signinSubmitBtn;
  }

  private async interactWithSigninError(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.signinError);
    if (!isVisible) throw new Error("Signin error is not visible!");
    return this.signinError;
  }

  // Form Toggle Links - InteractWhenVisible
  private async interactWithSwitchToSignupLink(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.switchToSignupLink);
    if (!isVisible) throw new Error("Switch to signup link is not visible!");
    return this.switchToSignupLink;
  }

  private async interactWithSwitchToSigninLink(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.switchToSigninLink);
    if (!isVisible) throw new Error("Switch to signin link is not visible!");
    return this.switchToSigninLink;
  }

  private async interactWithSwitchModeLink(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.switchModeLink);
    if (!isVisible) throw new Error("Switch mode link is not visible!");
    return this.switchModeLink;
  }

  // ==================== PUBLIC METHODS ====================

  // Email Authentication Button Actions
  async clickEmailAuthBtn(): Promise<void> {
    const element = await this.interactWithEmailAuthBtn();
    await element.click();
  }

  // Email Signup Form Functions
  async fillFirstName(firstName: string): Promise<void> {
    const element = await this.interactWithFirstNameInput();
    await element.fill(firstName);
  }

  async fillLastName(lastName: string): Promise<void> {
    const element = await this.interactWithLastNameInput();
    await element.fill(lastName);
  }

  async fillEmailField(email: string): Promise<void> {
    const element = await this.interactWithEmailSignupInput();
    await element.fill(email);
  }

  async fillPasswordField(password: string): Promise<void> {
    const element = await this.interactWithPasswordSignupInput();
    await element.fill(password);
  }

  async fillConfirmPasswordField(password: string): Promise<void> {
    const element = await this.interactWithConfirmPasswordInput();
    await element.fill(password);
  }

  async clickCreateAccountBtn(): Promise<void> {
    const element = await this.interactWithCreateAccountBtn();
    await element.click();
  }

  async getSignupErrorText(): Promise<string> {
    const element = await this.interactWithSignupError();
    return await element.textContent() || '';
  }

  async waitForSignupErrorVisible(): Promise<void> {
    await this.interactWithSignupError();
  }

  // Email Signin Form Functions
  async fillEmailFieldSignin(email: string): Promise<void> {
    const element = await this.interactWithEmailSigninInput();
    await element.fill(email);
  }

  async fillPasswordFieldSignin(password: string): Promise<void> {
    const element = await this.interactWithPasswordSigninInput();
    await element.fill(password);
  }

  async clickSignInBtn(): Promise<void> {
    const element = await this.interactWithSigninSubmitBtn();
    await element.click();
  }

  async getSigninErrorText(): Promise<string> {
    const element = await this.interactWithSigninError();
    return await element.textContent() || '';
  }

  async waitForSigninErrorVisible(): Promise<void> {
    await this.interactWithSigninError();
  }

  // Form State Functions
  async waitForEmailSignupFormVisible(): Promise<void> {
    await this.interactWithEmailSignupForm();
  }

  async waitForEmailSigninFormVisible(): Promise<void> {
    await this.interactWithEmailSigninForm();
  }

  async isSignupFormVisible(): Promise<boolean> {
    try {
      return await this.emailSignupForm.isVisible();
    } catch {
      return false;
    }
  }

  async isSigninFormVisible(): Promise<boolean> {
    try {
      return await this.emailSigninForm.isVisible();
    } catch {
      return false;
    }
  }

  // Form Toggle Actions
  async clickSwitchToSigninLink(): Promise<void> {
    const element = await this.interactWithSwitchToSigninLink();
    await element.click();
  }

  async clickSwitchToSignupLink(): Promise<void> {
    const element = await this.interactWithSwitchToSignupLink();
    await element.click();
  }

  async clickSwitchModeLink(): Promise<void> {
    const element = await this.interactWithSwitchModeLink();
    await element.click();
  }

  // User Information
  async getUserEmail(): Promise<string> {
    return await this.userEmailDisplay.textContent() || '';
  }
}
