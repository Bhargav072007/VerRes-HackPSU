import { test, expect } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`landing at ${width}px, validation and samples`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Proof, not vibes." }),
    ).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator("[data-reveal]").last()).toHaveCSS(
      "opacity",
      "1",
    );
    await page.screenshot({
      path: testInfo.outputPath(`landing-${width}.png`),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("not a PDF"),
      });
    await expect(page.locator("#submission-error")).toHaveText(
      "Please choose a PDF file.",
    );
    await page.screenshot({
      path: testInfo.outputPath(`invalid-file-${width}.png`),
      fullPage: true,
    });
    await page
      .getByLabel("arXiv ID or DOI", { exact: true })
      .fill("not-an-identifier");
    await page.getByRole("button", { name: "Review my paper" }).click();
    await expect(page.locator("#submission-error")).toHaveText(
      "Enter an arXiv ID or DOI",
    );
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "large.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.alloc(25 * 1024 * 1024 + 1),
      });
    await expect(page.locator("#submission-error")).toContainText("exceeds 25MB");
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "paper.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.4"),
      });
    await expect(page.getByRole("button", { name: "paper.pdf" })).toBeVisible();
    await expect(page.locator("#submission-error")).toHaveCount(0);
    const transfer = await page.evaluateHandle(() => {
      const transfer = new DataTransfer();
      transfer.items.add(
        new File(["invalid"], "dropped.txt", { type: "text/plain" }),
      );
      return transfer;
    });
    await page
      .locator(".drop-zone")
      .dispatchEvent("drop", { dataTransfer: transfer });
    await expect(page.locator("#submission-error")).toHaveText(
      "Please choose a PDF file.",
    );
    for (const sample of [
      "Clean paper",
      "Retracted reference",
      "Planted problems",
    ]) {
      await page.getByRole("button", { name: sample }).click();
      await expect(page.getByRole("status")).toContainText(
        "Sample papers will be available soon.",
      );
    }
    expect(errors).toEqual([]);
  });
}

test("reduced motion shows every word immediately and disables CSS animations", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const word of await page.locator("[data-reveal]").all()) {
    await expect(word).toHaveCSS("opacity", "1");
    await expect(word).toHaveCSS("transform", "none");
  }
  await page.getByRole("button", { name: /Drop your paper here/ }).hover();
  await expect(page.locator(".shimmer")).toHaveCSS("transition-duration", "0s");
  await page.screenshot({
    path: testInfo.outputPath("reduced-motion.png"),
    fullPage: true,
  });
});

test("check page is an explicit placeholder and safely renders the review ID", async ({
  page,
}) => {
  await page.goto("/check/submitted-paper-1");
  await expect(
    page.getByRole("heading", { name: "Your paper is in." }),
  ).toBeVisible();
  await expect(page.getByText("Review ID: submitted-paper-1")).toBeVisible();
  await page.getByRole("link", { name: "Back to VerRes" }).click();
  await expect(
    page.getByRole("heading", { name: "Proof, not vibes." }),
  ).toBeVisible();
});
