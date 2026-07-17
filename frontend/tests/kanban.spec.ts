import { expect, test, type Page } from "@playwright/test";

const INITIAL_BOARD = {
  columns: [
    { id: "col-backlog", title: "Backlog", cardIds: ["card-1", "card-2"] },
    { id: "col-discovery", title: "Discovery", cardIds: ["card-3"] },
    { id: "col-progress", title: "In Progress", cardIds: ["card-4", "card-5"] },
    { id: "col-review", title: "Review", cardIds: ["card-6"] },
    { id: "col-done", title: "Done", cardIds: ["card-7", "card-8"] },
  ],
  cards: {
    "card-1": {
      id: "card-1",
      title: "Align roadmap themes",
      details: "Draft quarterly themes with impact statements and metrics.",
    },
    "card-2": {
      id: "card-2",
      title: "Gather customer signals",
      details: "Review support tags, sales notes, and churn feedback.",
    },
    "card-3": {
      id: "card-3",
      title: "Prototype analytics view",
      details: "Sketch initial dashboard layout and key drill-downs.",
    },
    "card-4": {
      id: "card-4",
      title: "Refine status language",
      details: "Standardize column labels and tone across the board.",
    },
    "card-5": {
      id: "card-5",
      title: "Design card layout",
      details: "Add hierarchy and spacing for scanning dense lists.",
    },
    "card-6": {
      id: "card-6",
      title: "QA micro-interactions",
      details: "Verify hover, focus, and loading states.",
    },
    "card-7": {
      id: "card-7",
      title: "Ship marketing page",
      details: "Final copy approved and asset pack delivered.",
    },
    "card-8": {
      id: "card-8",
      title: "Close onboarding sprint",
      details: "Document release notes and share internally.",
    },
  },
};

const login = async (page: Page) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  const resetResponse = await page.request.put("/api/board", {
    data: INITIAL_BOARD,
  });
  expect(resetResponse.ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
};

test("redirects unauthenticated users to login", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("loads the kanban board", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("adds a card to a column", async ({ page }) => {
  await login(page);
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Playwright card");
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText("Playwright card")).toBeVisible();
});

test("moves a card between columns", async ({ page }) => {
  await login(page);
  const card = page.getByTestId("card-card-1");
  const targetColumn = page.getByTestId("column-col-review");
  const cardBox = await card.boundingBox();
  const columnBox = await targetColumn.boundingBox();
  if (!cardBox || !columnBox) {
    throw new Error("Unable to resolve drag coordinates.");
  }

  await page.mouse.move(
    cardBox.x + cardBox.width / 2,
    cardBox.y + cardBox.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    columnBox.x + columnBox.width / 2,
    columnBox.y + 120,
    { steps: 12 }
  );
  await page.mouse.up();
  await expect(targetColumn.getByTestId("card-card-1")).toBeVisible();
});

test("logs out and returns to login screen", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: /log out/i }).click();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("persists board changes after reload", async ({ page }) => {
  await login(page);

  const renamedTitle = "Backlog Persistent";
  const addedCardTitle = "Persistent card";

  const firstColumn = page.getByTestId("column-col-backlog");
  const reviewColumn = page.getByTestId("column-col-review");
  const waitForBoardSave = () =>
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/board") &&
        response.request().method() === "PUT" &&
        response.status() === 200
    );

  const titleInput = firstColumn.getByLabel("Column title");
  await titleInput.clear();
  await Promise.all([waitForBoardSave(), titleInput.fill(renamedTitle)]);

  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill(addedCardTitle);
  await firstColumn.getByPlaceholder("Details").fill("Should survive reload.");
  await Promise.all([
    waitForBoardSave(),
    firstColumn.getByRole("button", { name: /add card/i }).click(),
  ]);
  await expect(firstColumn.getByText(addedCardTitle)).toBeVisible();

  await Promise.all([
    waitForBoardSave(),
    firstColumn.getByLabel("Delete Gather customer signals").click(),
  ]);
  await expect(firstColumn.getByText("Gather customer signals")).toHaveCount(0);

  const card = page.getByTestId("card-card-1");
  const cardBox = await card.boundingBox();
  const columnBox = await reviewColumn.boundingBox();
  if (!cardBox || !columnBox) {
    throw new Error("Unable to resolve drag coordinates for persistence test.");
  }

  await page.mouse.move(cardBox.x + cardBox.width / 2, cardBox.y + cardBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(columnBox.x + columnBox.width / 2, columnBox.y + 120, {
    steps: 12,
  });
  await Promise.all([waitForBoardSave(), page.mouse.up()]);
  await expect(reviewColumn.getByTestId("card-card-1")).toBeVisible();

  await page.reload();

  await expect(page.getByTestId("column-col-backlog").getByLabel("Column title")).toHaveValue(
    renamedTitle
  );
  await expect(page.getByTestId("column-col-backlog").getByText(addedCardTitle)).toBeVisible();
  await expect(page.getByTestId("column-col-backlog").getByText("Gather customer signals")).toHaveCount(0);
  await expect(page.getByTestId("column-col-review").getByTestId("card-card-1")).toBeVisible();
});

test("uses AI sidebar for chat-only request", async ({ page }) => {
  test.setTimeout(120000);
  await login(page);

  const sidebar = page.getByTestId("ai-chat-sidebar");
  await expect(sidebar).toBeVisible();
  await expect(sidebar.getByTestId("ai-empty-state")).toBeVisible();

  const waitForAiResponse = () =>
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/ai/respond") &&
        response.request().method() === "POST" &&
        response.status() === 200
    );

  await sidebar.getByTestId("ai-input").fill("What is the purpose of this Kanban board?");
  await Promise.all([waitForAiResponse(), sidebar.getByTestId("ai-send").click()]);

  await expect(sidebar.getByTestId("ai-message-user").last()).toContainText(
    "What is the purpose of this Kanban board?"
  );
  await expect(sidebar.getByTestId("ai-message-assistant").last()).toBeVisible();
  await expect(sidebar.getByTestId("ai-operation-count")).toContainText("No changes");
});

test("uses AI sidebar for mutation and reflects board update with persistence", async ({ page }) => {
  test.setTimeout(120000);
  await login(page);

  const sidebar = page.getByTestId("ai-chat-sidebar");
  const backlogColumn = page.getByTestId("column-col-backlog");
  const progressColumn = page.getByTestId("column-col-progress");

  const waitForAiResponse = () =>
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/ai/respond") &&
        response.request().method() === "POST" &&
        response.status() === 200
    );

  await sidebar
    .getByTestId("ai-input")
    .fill("Create a card named AI E2E card in the Backlog column.");
  await Promise.all([waitForAiResponse(), sidebar.getByTestId("ai-send").click()]);

  await expect(backlogColumn.getByText("AI E2E card")).toBeVisible();
  await expect(sidebar.getByTestId("ai-operation-count")).toContainText("1 change");

  await sidebar
    .getByTestId("ai-input")
    .fill("Move the AI E2E card to In Progress.");
  await Promise.all([waitForAiResponse(), sidebar.getByTestId("ai-send").click()]);

  await expect(progressColumn.getByText("AI E2E card")).toBeVisible();

  await page.reload();
  await expect(progressColumn.getByText("AI E2E card")).toBeVisible();
});
