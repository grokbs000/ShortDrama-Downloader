import asyncio
from playwright.async_api import async_playwright

ARTIFACT_DIR = "/Users/banson/.gemini/antigravity-ide/brain/d97f738a-7c7c-461a-9aaa-811fe6934ef5"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        print("[1] Navigating to http://127.0.0.1:8765 ...")
        await page.goto("http://127.0.0.1:8765", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 1. Switch to Flex TV
        print("[2] Switching to Flex TV ...")
        await page.click("#nav-platform-flextv")
        await page.wait_for_selector(".drama-card", timeout=10000)
        await page.wait_for_timeout(2000)

        # Verify no top bar
        assert not await page.is_visible("#platform-segmented-bar"), "Top segmented bar should not exist!"

        # 2. Check cards and click checkboxes
        print("[3] Selecting 2 drama cards ...")
        cards = await page.query_selector_all(".drama-card")
        print(f"Found {len(cards)} drama cards on page.")
        assert len(cards) >= 2, "Should have at least 2 drama cards"

        check_boxes = await page.query_selector_all(".drama-select-check")
        assert len(check_boxes) >= 2, "Each card must have select checkbox"
        
        await check_boxes[0].click()
        await page.wait_for_timeout(300)
        await check_boxes[1].click()
        await page.wait_for_timeout(500)

        # 3. Verify floating batch bar
        batch_bar = await page.query_selector("#floating-batch-bar")
        is_visible = await batch_bar.evaluate("el => el.classList.contains('visible')")
        print(f"Batch bar visible: {is_visible}")
        assert is_visible, "Floating batch bar should be visible after selecting dramas"
        
        count_text = await page.inner_text("#batch-selected-count")
        print(f"Selected count in bar: {count_text}")
        assert count_text == "2", "Should show 2 selected dramas"

        await page.screenshot(path=f"{ARTIFACT_DIR}/batch_bar_selected.png")
        print(f"Saved {ARTIFACT_DIR}/batch_bar_selected.png")

        # 4. Open Episode Drawer on first drama
        print("[4] Opening Episode Drawer ...")
        # Click the title or cover (avoid checkbox)
        thumb = await cards[0].query_selector(".drama-thumb")
        await thumb.click()
        await page.wait_for_selector(".drawer-backdrop.active", timeout=10000)
        await page.wait_for_timeout(1000)

        # Verify undownloaded button and skip downloaded checkbox
        assert await page.is_visible("#btn-select-undownloaded"), "Drawer undownloaded button should exist"
        assert await page.is_visible("#drawer-skip-downloaded-cb"), "Drawer skip downloaded checkbox should exist"
        print("Drawer undownloaded button and checkbox verified!")

        await page.screenshot(path=f"{ARTIFACT_DIR}/drawer_undownloaded_verified.png")
        print(f"Saved {ARTIFACT_DIR}/drawer_undownloaded_verified.png")

        # Close drawer
        await page.click("button:has-text('✕ 關閉')")
        await page.wait_for_timeout(500)

        # 5. Navigate to Settings page
        print("[5] Navigating to Settings ...")
        await page.click("#nav-settings")
        await page.wait_for_timeout(1000)

        min_val = await page.input_value("#setting-delay-min")
        max_val = await page.input_value("#setting-delay-max")
        print(f"Crawler delay settings: min={min_val}s, max={max_val}s")
        assert min_val == "0.8" and (max_val == "2" or max_val == "2.0"), f"Delay should be 0.8 and 2, got {min_val}, {max_val}"

        await page.screenshot(path=f"{ARTIFACT_DIR}/settings_delay_verified.png")
        print(f"Saved {ARTIFACT_DIR}/settings_delay_verified.png")

        print("🎉 ALL UI VERIFICATIONS PASSED SUCCESSFULLY!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
