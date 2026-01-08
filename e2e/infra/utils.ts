import { Locator } from "playwright";

export function delay(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export const waitForElementToBeVisible = async (
  locator: Locator,
  time = 500,
  retry = 10
): Promise<boolean> => {
  for (let i = 0; i < retry; i += 1) {
    try {
      if (await locator.isVisible()) {
        return true;
      }
    } catch (error) {
      console.error(`Error checking element visibility: ${error}`);
    }
    await delay(time);
  }
  return false;
};

export const waitForElementToNotBeVisible = async (
  locator: Locator,
  time = 500,
  retry = 10
): Promise<boolean> => {
  for (let i = 0; i < retry; i += 1) {
    try {
      if (!(await locator.isVisible())) {
        return true;
      }
    } catch (error) {
      console.error(`Error checking element visibility: ${error}`);
    }
    await delay(time);
  }
  return false;
};

export const waitForElementToBeEnabled = async (
  locator: Locator,
  time = 500,
  retry = 10
): Promise<boolean> => {
  for (let i = 0; i < retry; i += 1) {
    try {
      if (await locator.isEnabled()) {
        return true;
      }
    } catch (error) {
      console.error(`Error checking element enabled: ${error}`);
    }
    await delay(time);
  }
  return false;
};

export function getRandomString(prefix = "", delimiter = "_"): string {
  const uuid = crypto.randomUUID();
  const timestamp = Date.now();
  return `${prefix}${prefix ? delimiter : ""}${uuid}-${timestamp}`;
}
