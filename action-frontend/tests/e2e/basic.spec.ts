import { test, expect } from '@playwright/test'

test('loads sessions page', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('text=Sessions')).toBeVisible()
})


