import { Locator, expect } from "@playwright/test";

export function delay(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

// `time` and `retry` are kept for call-site compatibility: they define the total budget.
// Floored at 1ms because Playwright reads `timeout: 0` as "no timeout", which
// would turn a zero argument into a wait for the whole test rather than an
// immediate `false`.
const budget = (time: number, retry: number) => Math.max(1, time * retry);

export const waitForElementToBeVisible = async (
  locator: Locator,
  time = 500,
  retry = 10
): Promise<boolean> => {
  try {
    await locator.waitFor({ state: "visible", timeout: budget(time, retry) });
    return true;
  } catch {
    return false;
  }
};

export const waitForElementToNotBeVisible = async (
  locator: Locator,
  time = 500,
  retry = 10
): Promise<boolean> => {
  try {
    await locator.waitFor({ state: "hidden", timeout: budget(time, retry) });
    return true;
  } catch {
    return false;
  }
};

export const waitForElementToBeEnabled = async (
  locator: Locator,
  time = 500,
  retry = 10
): Promise<boolean> => {
  try {
    await expect(locator).toBeEnabled({ timeout: budget(time, retry) });
    return true;
  } catch {
    return false;
  }
};

export function getRandomString(prefix = "", delimiter = "_"): string {
  const uuid = crypto.randomUUID();
  const timestamp = Date.now();
  return `${prefix}${prefix ? delimiter : ""}${uuid}-${timestamp}`;
}
