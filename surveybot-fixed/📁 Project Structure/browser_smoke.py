"""Exercise the actual browser-action pipeline using an isolated local fixture."""
import html
import json
import re
from types import SimpleNamespace

from playwright.async_api import async_playwright
from bot_implementations import survey_bot_playwright as bot

FIXTURE = """<!doctype html><html><body>
<p>Local test only: select Option B and enter the fixture note.</p>
<input type="radio" name="choice" id="option-a"><label for="option-a">Option A</label>
<input type="radio" name="choice" id="option-b"><label for="option-b">Option B</label>
<label for="notes">Fixture note</label><input id="notes" type="text">
<button id="advance" onclick="document.getElementById('result').textContent = document.getElementById('option-b').checked && document.getElementById('notes').value === 'Local fixture note' ? 'complete' : 'wrong'">Continue</button>
<p id="result">pending</p></body></html>"""


class FixtureModel:
    def __init__(self, target, text=None):
        self.target = target
        self.text = text

    async def generate_content_async(self, contents):
        prompt = contents[0]
        if self.target == "invalid":
            return SimpleNamespace(text=json.dumps({"tool": "click_element", "args": {"element_id": 999999}}))
        if self.target == "malformed":
            return SimpleNamespace(text="not a JSON action")
        patterns = {
            "option": r'\[(\d+)\] <label> "Option B"',
            "note": r'\[(\d+)\] <input> "[^\n]*id: notes',
            "continue": r'\[(\d+)\] <button> "Continue"',
        }
        match = re.search(patterns[self.target], prompt)
        if match is None:
            raise AssertionError("The real DOM extractor did not expose the fixture control.")
        action = {"tool": "fill_textbox" if self.target == "note" else "click_element", "args": {"element_id": int(match[1])}}
        if self.text is not None:
            action["args"]["text_to_fill"] = self.text
        return SimpleNamespace(text=json.dumps(action))


async def run_smoke_test():
    original_model = bot.model
    checks = 0
    try:
        async with async_playwright() as playwright:
            browser = await getattr(playwright, bot.Config.BROWSER_NAME).launch(**bot.launch_options(headless=True))
            try:
                context = await browser.new_context()
                # Nothing in this check may access Qmee or any external service.
                await context.route("http://**/*", lambda route: route.abort())
                await context.route("https://**/*", lambda route: route.abort())
                page = await context.new_page()
                await page.set_content('<iframe title="signup-survey" srcdoc="' + html.escape(FIXTURE, quote=True) + '"></iframe>')
                frame = page.frame_locator('iframe[title="signup-survey"]')
                await frame.locator("#option-b").wait_for()
                for target in ["invalid", "malformed"]:
                    bot.model = FixtureModel(target)
                    assert await bot.solve_page_with_hybrid_vision_dom(frame, page) is False
                    assert not await frame.locator("#option-a").is_checked()
                    assert await frame.locator("#result").inner_text() == "pending"
                    checks += 1
                for target, text in [("option", None), ("note", "Local fixture note"), ("continue", None)]:
                    bot.model = FixtureModel(target, text)
                    assert await bot.solve_page_with_hybrid_vision_dom(frame, page) is True
                    checks += 1
                assert await frame.locator("#option-b").is_checked()
                assert await frame.locator("#notes").input_value() == "Local fixture note"
                assert await frame.locator("#result").inner_text() == "complete"
                await context.close()
            finally:
                await browser.close()
        print(f"PASS: {checks} browser checks using the real DOM/action pipeline and a simulated AI model.")
        print("No survey account, credentials, remote API, or paid survey was used.")
        return 0
    finally:
        bot.model = original_model
