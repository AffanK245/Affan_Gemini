import asyncio
import os
from playwright.async_api import async_playwright

async def record_demo():
    output_dir = "/tmp/demo_videos"
    os.makedirs(output_dir, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=output_dir,
            record_video_size={"width": 1280, "height": 720}
        )
        
        page = await context.new_page()
        print("Navigating to frontend...")
        await page.goto("http://localhost:8080")
        await page.wait_for_timeout(2000)
        
        # 1. First interaction: Click prompt button
        print("Sending Prompt 1...")
        prompt1_btn = page.locator(".prompt-btn", has_text="Find top destinations in Japan")
        if await prompt1_btn.is_visible():
            await prompt1_btn.click()
        else:
            await page.fill("#input", "Find top destinations in Japan")
            await page.click(".send-btn")
            
        # Wait for agent response
        print("Waiting for Prompt 1 response...")
        await page.wait_for_selector(".msg.agent", timeout=40000)
        await page.wait_for_timeout(8000)
        
        # 2. Second interaction: Rich prompt asking for trip calculation and destination video/photo
        print("Sending Prompt 2...")
        prompt2 = "Can you calculate a 5-day budget for Paris and generate a scenic preview video of the Eiffel Tower?"
        await page.fill("#input", prompt2)
        await page.wait_for_timeout(1500)
        await page.click(".send-btn")
        
        # Wait for tool execution and response
        print("Waiting for Prompt 2 response...")
        await page.wait_for_timeout(25000)
        await page.wait_for_timeout(3000)
        
        video_obj = page.video
        await context.close()
        await browser.close()
        
        if video_obj:
            saved_path = await video_obj.path()
            print(f"Recorded video saved to: {saved_path}")
            
            # Convert webm to mp4 if ffmpeg is available
            mp4_path = os.path.join(output_dir, "travel_concierge_demo.mp4")
            os.system(f"ffmpeg -y -i {saved_path} -c:v libx264 -pix_fmt yuv420p {mp4_path} >/dev/null 2>&1")
            if os.path.exists(mp4_path):
                print(f"Converted MP4 demo video created at: {mp4_path}")

if __name__ == "__main__":
    asyncio.run(record_demo())
