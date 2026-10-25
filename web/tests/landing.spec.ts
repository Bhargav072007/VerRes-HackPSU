import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

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
      page.getByRole("heading", { name: "Read your paper like Reviewer 2 would." }),
    ).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator("h1[data-reveal]")).toHaveCSS(
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
  await page.getByRole("button", { name: /Choose PDF/ }).hover();
  await expect(page.locator(".hero-laptop")).toHaveCSS("transform", "none");
  await page.screenshot({
    path: testInfo.outputPath("reduced-motion.png"),
    fullPage: true,
  });
});

for (const [label, filename] of [
  ["Attention Is All You Need", "paper1_attention.pdf"],
  ["Cites a retracted paper", "paper2_retracted_reference.pdf"],
  ["Planted problems", "paper3_planted_problems.pdf"],
]) test(`sample ${filename} sends its actual PDF through multipart intake`, async ({ page }) => {
  const pdf = readFileSync(`public/samples/${filename}`);
  const events = readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").slice(0, 6).map(line => JSON.parse(line));
  await page.route("**/jobs/sample", route => route.fulfill({ json: { events } }));
  await page.route("**/jobs/sample/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.route("**/jobs", async route => {
    const request = route.request();
    expect(request.method()).toBe("POST");
    expect(request.headers()["content-type"]).toContain("multipart/form-data; boundary=");
    expect(request.postDataBuffer()!.includes(Buffer.from(`name="file"; filename="${filename}"`))).toBe(true);
    expect(request.postDataBuffer()!.includes(pdf)).toBe(true);
    await route.fulfill({ status: 202, json: { job_id: "sample" } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: label, exact: true }).click();
  await expect(page).toHaveURL("/check/sample");
  await expect(page.locator("[data-reference-id]")).toHaveCount(3);
});

test("sample loading and intake failures explain how to retry", async ({ page }) => {
  await page.route("**/samples/paper1_attention.pdf", route => route.fulfill({ body: "", contentType: "application/pdf" }));
  await page.goto("/");
  await page.getByRole("button", { name: "Attention Is All You Need" }).click();
  await expect(page.locator("#submission-error")).toContainText("This PDF is empty");
  await expect(page.getByRole("button", { name: "Review my paper" })).toBeEnabled();
  await page.route("**/jobs", route => route.fulfill({ json: { code: "CHECK_INCOMPLETE", message: "The review service is busy. Please try again." } }));
  await page.getByRole("button", { name: "Planted problems" }).click();
  await expect(page.locator("#submission-error")).toContainText("Please try again");
  await expect(page.getByRole("button", { name: "Planted problems" })).toBeEnabled();
});
