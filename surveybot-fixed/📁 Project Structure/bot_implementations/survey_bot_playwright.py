import asyncio
import os
import json
import re
import shutil
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from config import Config
from gemini_support import GeminiModel, get_api_key
import actions
from personality_responses import generate_personality_response

GOOGLE_API_KEY = get_api_key()
USE_GEMINI_API = bool(GOOGLE_API_KEY)
model = GeminiModel(Config.AI_MODEL, json_output=True) if USE_GEMINI_API else None
# Profiles are loaded at live startup, not during module import or offline checks.
PERSONA = {}
PERSONA_PROMPT = "Use only the profile facts provided. If facts are missing, choose no_action."


def load_persona():
    global PERSONA, PERSONA_PROMPT
    with Config.PERSONA_FILE.open(encoding="utf-8") as stream:
        profile = json.load(stream)
    if not isinstance(profile, dict):
        raise ValueError("persona.json must contain a JSON object.")
    PERSONA = profile
    PERSONA_PROMPT = (
        "Answer using only these user-provided profile facts: " + json.dumps(profile) +
        ". Do not invent personal information. If an answer needs missing facts, choose no_action. "
        "Use the numeric element ID from the DOM tree for each action."
    )


# <<< FINAL FIX HERE: Fixed f-string syntax in build_dom_tree >>>
async def build_dom_tree(element, element_map, indent=""):
    try:
        tag = await element.evaluate('node => node.tagName.toLowerCase()')
        
        text = ""
        if tag == 'input':
            input_type = await element.get_attribute('type')
            if input_type in ['text', 'number', 'email', 'password']:
                text = f"Input (Placeholder: {await element.get_attribute('placeholder') or input_type})"
            elif input_type in ['radio', 'checkbox']:
                label_text = await element.evaluate('''
                    (node) => {
                        const id = node.id;
                        if (id) {
                            const label = document.querySelector(`label[for="${id}"]`);
                            if (label) return label.textContent.trim().split('\\n')[0];
                        }
                        return node.value || node.textContent.trim().split('\\n')[0];
                    }
                ''')
                text = f"{input_type.capitalize()} (Value: {label_text or await element.get_attribute('value') or ''})"
        elif tag == 'select':
            selected_option_full = await element.get_by_role('combobox').inner_text() or ""
            # <<< FIX HERE: Process string BEFORE putting into f-string >>>
            selected_option_first_line = selected_option_full.strip().split('\n')[0] 
            text = f"Dropdown Select (Current: \"{selected_option_first_line}\")"
        elif tag == 'button':
            text = (await element.inner_text() or await element.get_attribute('name') or "Button").strip().split('\n')[0]
        elif tag == 'a':
            text = (await element.inner_text() or await element.get_attribute('aria-label') or await element.get_attribute('href') or "Link").strip().split('\n')[0]
        elif tag == 'label':
             text = (await element.inner_text() or await element.get_attribute('aria-label') or "").strip().split('\n')[0]
        elif tag in ['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text = await element.evaluate('node => node.textContent.trim().split("\\n")[0]')
        
        if not await element.is_visible() or tag in ['script', 'style', 'meta', 'link']:
            return ""

        if not text or len(text) < 1:
            return ""

        element_id = len(element_map)
        element_map[element_id] = element
        
        # Debug: Print what we're finding
        if tag in ['button', 'input', 'select', 'a']:
            print(f"Found interactive element [{element_id}]: <{tag}> '{text}'")
        
        # Add more context for interactive elements
        if tag in ['button', 'input', 'select', 'a']:
            additional_info = ""
            if tag == 'button':
                button_type = await element.get_attribute('type') or 'button'
                additional_info = f" (type: {button_type})"
            elif tag == 'input':
                input_type = await element.get_attribute('type') or 'text'
                additional_info = f" (type: {input_type})"
            
            tree_text = f'{indent}[{element_id}] <{tag}{additional_info}> "{text}"\n'
        else:
            tree_text = f'{indent}[{element_id}] <{tag}> "{text}"\n'

        if tag not in ['input', 'button', 'select', 'textarea', 'a', 'label']:
            children = await element.query_selector_all(':scope > *')
            for child in children:
                tree_text += await build_dom_tree(child, element_map, indent + "  ")
        
        return tree_text
    except Exception:
        return ""

async def solve_page_with_hybrid_vision_dom(context, main_page):
    print("Handling page with Hybrid Vision/DOM Model...")
    try:
        await asyncio.sleep(0.5) 
        screenshot = await main_page.screenshot(type="png", full_page=True)
        
        element_map = {}
        
        # Always try to get the iframe first
        iframe_locator = main_page.frame_locator('iframe[title="signup-survey"]')
        try:
            await iframe_locator.locator('body').wait_for(timeout=5000)
            # Wait a bit more for iframe content to fully load
            await asyncio.sleep(2)
            print("Found iframe, using iframe context")
            
            # Debug: Check what's actually in the iframe
            try:
                iframe_text = await iframe_locator.locator('body').inner_text()
                print(f"Iframe body text preview: {iframe_text[:200]}...")
            except Exception as e:
                print(f"Could not get iframe text: {e}")
            
            # Check for interactive elements in iframe
            try:
                buttons = await iframe_locator.locator('button').all()
                inputs = await iframe_locator.locator('input').all()
                links = await iframe_locator.locator('a').all()
                print(f"Found in iframe: {len(buttons)} buttons, {len(inputs)} inputs, {len(links)} links")
            except Exception as e:
                print(f"Could not count iframe elements: {e}")
            
            body = await iframe_locator.locator('body').element_handle()
            context = iframe_locator  # Use iframe as context for element interactions
        except Exception as e:
            print(f"Could not find iframe, using main page: {e}")
            body = await main_page.locator('body').element_handle()
        
        # Try a simpler approach - directly get interactive elements
        print("Building DOM tree with direct element selection...")
        
        # Get all interactive elements directly
        buttons = await context.locator('button').all()
        inputs = await context.locator('input').all()
        textareas = await context.locator('textarea').all()
        selects = await context.locator('select').all()
        links = await context.locator('a').all()
        labels = await context.locator('label').all()
        
        all_elements = buttons + inputs + textareas + selects + links + labels
        print(f"Found {len(all_elements)} total interactive elements")
        
        # Build a simple DOM tree from these elements
        dom_tree_text = ""
        for i, element in enumerate(all_elements):
            try:
                tag = await element.evaluate('node => node.tagName.toLowerCase()')
                
                if tag == 'input':
                    input_type = await element.get_attribute('type') or 'text'
                    placeholder = await element.get_attribute('placeholder') or ''
                    value = await element.get_attribute('value') or ''
                    name = await element.get_attribute('name') or ''
                    id_attr = await element.get_attribute('id') or ''
                    text = f"Input (type: {input_type}, placeholder: {placeholder}, value: {value}, name: {name}, id: {id_attr})"
                elif tag == 'textarea':
                    placeholder = await element.get_attribute('placeholder') or ''
                    value = await element.get_attribute('value') or ''
                    name = await element.get_attribute('name') or ''
                    id_attr = await element.get_attribute('id') or ''
                    text = f"Textarea (placeholder: {placeholder}, value: {value}, name: {name}, id: {id_attr})"
                elif tag == 'button':
                    text = await element.inner_text() or await element.get_attribute('name') or 'Button'
                elif tag == 'select':
                    text = await element.inner_text() or 'Dropdown'
                elif tag == 'a':
                    text = await element.inner_text() or await element.get_attribute('href') or 'Link'
                elif tag == 'label':
                    text = await element.inner_text() or 'Label'
                else:
                    text = await element.inner_text() or tag
                
                # Clean up text
                text = text.strip().split('\n')[0][:100]  # Limit length
                
                if text and len(text) > 1:
                    element_map[i] = element
                    dom_tree_text += f"[{i}] <{tag}> \"{text}\"\n"
                    print(f"Added element [{i}]: <{tag}> '{text}'")
                    
            except Exception as e:
                print(f"Error processing element {i}: {e}")
                continue
        
        print(f"Built DOM tree with {len(element_map)} elements")
        
        tools_prompt = """
        You have these tools:
        1. `click_element(element_id)`: Use for buttons, links, radio buttons, or checkboxes.
        2. `fill_textbox(element_id, text_to_fill)`: Use for text fields (input type="text", "email", "password" or textarea).

        Based on the user's persona, the screenshot, and the DOM tree, decide the single best action to progress through the survey.
        When specifying 'element_id', you MUST use the NUMERIC ID (e.g., 15) provided in the DOM tree, NOT its text label.
        You MUST respond in a valid JSON format with "tool" and "args" keys.
        Example for clicking a "Next" button with ID 15: `{"tool": "click_element", "args": {"element_id": 15}}`
        Example for filling a zipcode field with ID 5: `{"tool": "fill_textbox", "args": {"element_id": 5, "text_to_fill": "90001"}}`
        If no action is clear, respond with: `{"tool": "no_action", "args": {}}`
        
        IMPORTANT: 
        - For radio buttons, prefer clicking the LABEL element (which is visible) rather than the hidden radio input
        - For checkboxes, prefer clicking the LABEL element rather than the hidden checkbox input
        - Only select elements that are clearly visible and interactive
        - If you're unsure about which element to select, choose "no_action" rather than guessing
        - Leave consent and eligibility decisions to the user when their intent or profile facts are missing
        - Fill text fields only after answering any consent questions
        - For open-ended questions, use only user-provided facts; choose no_action if the facts are insufficient
        - PRIORITY: If you see a text input field (input type="text" or textarea) and a submit button, ALWAYS fill the text field first, then click the submit button
        - For text input pages, look for the largest or most prominent text input field to fill
        """
        prompt = f"""
        {PERSONA_PROMPT}
        {tools_prompt}
        Here is the structured DOM tree of the webpage:
        ---
        {dom_tree_text}
        ---
        Analyze the screenshot AND the DOM tree, then choose the tool to use. Respond with only the JSON object.
        """
        
        if model is None:
            print("Gemini is not configured. No page action was taken.")
            return False

        try:
            response = await model.generate_content_async([prompt, {"mime_type": "image/png", "data": screenshot}])
            print(f"AI Response: {response.text}")
        except Exception as e:
            print(f"Error calling AI API: {e}")
            return False
        
        try:
            decision_json = json.loads(response.text)
        except json.JSONDecodeError:
            print(f"Error: AI returned invalid JSON: {response.text}")
            return False
        if not isinstance(decision_json, dict):
            print("AI returned an invalid action object. No page action was taken.")
            return False

        tool_name = decision_json.get('tool')
        raw_element_id = decision_json.get('args', {}).get('element_id')
        text_to_fill = decision_json.get('args', {}).get('text_to_fill')

        if not tool_name:
            print(f"Error: AI response missing 'tool'. Response: {decision_json}")
            return False
            
        if tool_name == "no_action":
            print("AI decided no action was possible.")
            return False
            
        if raw_element_id is None:
            print(f"Error: AI response missing 'element_id'. Response: {decision_json}")
            return False

        if isinstance(raw_element_id, bool) or not isinstance(raw_element_id, (int, str)):
            print("AI returned an invalid element ID. No page action was taken.")
            return False
        try:
            element_id_int = int(raw_element_id)
        except ValueError:
            print("AI returned a non-numeric element ID. No page action was taken.")
            return False
        element_to_interact = element_map.get(element_id_int)
        if element_to_interact is None:
            print("AI selected an element that is not on the page. No page action was taken.")
            return False

        print(f"AI chose tool: {tool_name} for element '{raw_element_id}'")

        if tool_name == "click_element":
            # Find the element_id for the element_to_interact
            element_id = None
            for eid, elem in element_map.items():
                if elem == element_to_interact:
                    element_id = eid
                    break
            
            if element_id is not None:
                await actions.click_element(context, element_id, element_map)
            else:
                print(f"Error: Could not find element_id for element in map")
                return False
        elif tool_name == "fill_textbox":
            # Find the element_id for the element_to_interact
            element_id = None
            for eid, elem in element_map.items():
                if elem == element_to_interact:
                    element_id = eid
                    break
            
            if element_id is None or not isinstance(text_to_fill, str):
                print("AI returned an invalid text-field action. No page action was taken.")
                return False
            await actions.fill_textbox(context, element_id, text_to_fill, element_map)
        elif tool_name == "no_action":
            print("AI decided no action was possible.")
            return False
        else:
            print(f"Error: AI chose an unknown tool: {tool_name}")
            return False

        return True

    except Exception as e:
        print(f"An error occurred in the Hybrid Vision/DOM model: {e}")
        return False

async def handle_date_of_birth_page(iframe, page, persona):
    print("Detected 'Date of birth' page. Handling the full sequence...")
    try:
        dob_str = persona['about_you']['date_of_birth']
        dob_obj = datetime.strptime(dob_str, '%Y-%m-%d')
        year = str(dob_obj.year)
        month = str(dob_obj.month)
        day = str(dob_obj.day)
        
        print(f"Persona DOB: {month}/{day}/{year}")

        await iframe.get_by_placeholder("MM").type(month, delay=100)
        print(f"Typed Month: {month}")

        await page.keyboard.press("Tab")
        await iframe.get_by_placeholder("DD").type(day, delay=100)
        print(f"Typed Day: {day}")

        await page.keyboard.press("Tab")
        await iframe.get_by_placeholder("YYYY").type(year, delay=100)
        print(f"Typed Year: {year}")
        
        print("Waiting for age confirmation question...")
        confirmation_button = iframe.get_by_role("button", name="Yes")
        await confirmation_button.wait_for(timeout=10000)
        
        print("Confirmation question found. Clicking 'Yes'.")
        await confirmation_button.click()
        
        print("Successfully submitted Date of Birth and confirmed age.")
        return True
    except Exception as e:
        print(f"An error occurred while handling Date of Birth page: {e}")
        return False

async def handle_address_page(iframe, page, persona):
    print("Detected 'Address' page. Handling the full sequence...")
    try:
        # First, click "Yes" to consent to providing full address
        print("Clicking 'Yes' to consent to providing full address...")
        
        # Try different ways to find the Yes button
        try:
            yes_button = iframe.get_by_role("button", name="Yes")
            await yes_button.wait_for(timeout=2000)
            await yes_button.click()
        except:
            try:
                yes_label = iframe.locator('label:has-text("Yes")')
                await yes_label.wait_for(timeout=2000)
                await yes_label.click()
            except:
                # Use the hybrid approach to find and click Yes
                print("Using hybrid approach to find Yes button...")
                return await solve_page_with_hybrid_vision_dom(iframe, page)
        
        # Wait for address fields to appear
        await asyncio.sleep(2)
        
        # Fill in the address fields
        zipcode = persona['about_you']['zipcode']
        city = persona['about_you']['city']
        state = persona['about_you']['state']
        
        # Create a street address based on persona data
        street_address = f"123 Main St, {city}, {state} {zipcode}"
        
        print(f"Filling address fields with: {street_address}")
        
        # Use comprehensive field detection to fill all form fields
        filled_fields = await detect_and_fill_form_fields(iframe, persona)
        
        # Also handle any specific fields that might not be caught by the general detection
        try:
            # Handle State dropdown specifically (since it might be a custom dropdown)
            state_dropdown = iframe.locator('select, input[placeholder*="State"], input[placeholder*="state"]')
            if await state_dropdown.is_visible(timeout=2000):
                print(f"Found state dropdown, selecting: {state}")
                await state_dropdown.click()
                await asyncio.sleep(1)
                
                # Try different approaches to select the state
                try:
                    # First try: look for a specific state option in dropdown
                    state_option = iframe.locator(f'[role="option"]:has-text("{state}"), option:has-text("{state}"), div[class*="option"]:has-text("{state}")')
                    await state_option.first.wait_for(timeout=3000)
                    await state_option.first.click()
                    print(f"Selected state: {state}")
                except:
                    try:
                        # Second try: type the state name
                        await state_dropdown.type(state)
                        await asyncio.sleep(1)
                        # Press Enter or Tab to confirm
                        await page.keyboard.press("Enter")
                        print(f"Typed and selected state: {state}")
                    except:
                        # Third try: use keyboard navigation
                        await state_dropdown.press("ArrowDown")
                        await asyncio.sleep(0.5)
                        # Press Enter to select
                        await page.keyboard.press("Enter")
                        print(f"Used keyboard navigation for state selection")
        except Exception as e:
            print(f"Could not handle state dropdown: {e}")
        
        # Look for a submit/continue button
        try:
            submit_button = iframe.locator('button:has-text("Submit"), button:has-text("Continue"), button:has-text("Next"), input[type="submit"]')
            if await submit_button.is_visible(timeout=2000):
                print("Found submit button, clicking...")
                await submit_button.click()
                print("Clicked submit button")
        except Exception as e:
            print(f"Could not find submit button: {e}")
        
        print("Successfully filled all address fields.")
        
        # Wait a bit for the form to process and see if we need to submit
        await asyncio.sleep(3)
        
        # Check if there are any submit buttons or if the page has changed
        try:
            submit_buttons = iframe.locator('button:has-text("Submit"), button:has-text("Continue"), button:has-text("Next"), button:has-text("Confirm"), input[type="submit"]')
            if await submit_buttons.count() > 0:
                print("Found submit button, clicking...")
                await submit_buttons.first.click()
                print("Clicked submit button")
                await asyncio.sleep(3)
            else:
                print("No submit button found - form may auto-submit")
        except Exception as e:
            print(f"No submit button found: {e}")
        
        # Wait a bit more for any page transitions
        await asyncio.sleep(2)
        print("Address form completed, waiting for next page...")
        
        # Wait a bit more to see if there are any additional pages
        await asyncio.sleep(5)
        

        
        return True
    except Exception as e:
        print(f"An error occurred while handling Address page: {e}")
        return False

async def handle_ethnicity_page(iframe, page, persona):
    """
    Handle the ethnicity selection page.
    """
    try:
        print("Detected 'Ethnicity' page. Handling ethnicity selection...")
        
        # Get ethnicity from persona
        ethnicity = persona.get("about_you", {}).get("ethnicity", "White / Caucasian")
        print(f"Persona ethnicity: {ethnicity}")
        
        # Map persona ethnicity to survey options
        ethnicity_mapping = {
            "White / Caucasian": "White/Caucasian",
            "Black or African-American": "Black or African-American", 
            "Asian American": "Asian American",
            "Native American or Alaskan Native": "Native American or Alaskan Native",
            "Pacific Islander": "Pacific Islander",
            "East Asian": "East Asian",
            "South Asian/Indian": "South Asian/Indian",
            "Filipino": "Filipino",
            "Other": "Other",
            "Don't know/prefer not to say": "Don't know/prefer not to say"
        }
        
        target_ethnicity = ethnicity_mapping.get(ethnicity, "White/Caucasian")
        print(f"Selecting ethnicity: {target_ethnicity}")
        
        # Print all clickable elements and their text for debugging
        clickable_elements = await iframe.locator('button, div, label, input[type="radio"]').all()
        print("[Ethnicity Debug] All clickable elements on page:")
        for idx, elem in enumerate(clickable_elements):
            try:
                text = await elem.inner_text()
                print(f"  [{idx}] {text}")
            except Exception:
                continue

        # Try to click the radio button directly
        try:
            # Get all radio buttons
            radio_buttons = iframe.locator('input[type="radio"]')
            radio_count = await radio_buttons.count()
            print(f"Found {radio_count} radio buttons")
            
            # Try to find the radio button for our ethnicity
            for i in range(radio_count):
                radio = radio_buttons.nth(i)
                try:
                    # Get the associated label
                    radio_id = await radio.get_attribute('id')
                    if radio_id:
                        label = iframe.locator(f'label[for="{radio_id}"]')
                        if await label.count() > 0:
                            label_text = await label.first.inner_text()
                            if target_ethnicity.lower() in label_text.lower():
                                await radio.click()
                                print(f"Clicked radio button for {target_ethnicity}")
                                await asyncio.sleep(2)
                                
                                # Try to find and click a next/continue button
                                next_buttons = iframe.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Submit")')
                                if await next_buttons.count() > 0:
                                    await next_buttons.first.click()
                                    print("Clicked next button after ethnicity selection")
                                    await asyncio.sleep(2)
                                
                                return True
                except Exception as e:
                    print(f"Failed to check radio button {i}: {e}")
        except Exception as e:
            print(f"Failed to find radio buttons: {e}")
        
        # If radio button approach fails, try clicking the specific element from debug output
        # Based on debug output, element [16] is "White/Caucasian"
        try:
            for idx, elem in enumerate(clickable_elements):
                try:
                    text = await elem.inner_text()
                    # Look for elements that contain exactly "White/Caucasian" or similar
                    if text.strip() == "White/Caucasian" or text.strip() == target_ethnicity:
                        print(f"Found exact ethnicity match at element [{idx}]: {text}")
                        await elem.click()
                        print(f"Clicked ethnicity element [{idx}] with text: {text}")
                        await asyncio.sleep(2)
                        
                        # Try to find and click a next/continue button
                        next_buttons = iframe.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Submit")')
                        if await next_buttons.count() > 0:
                            await next_buttons.first.click()
                            print("Clicked next button after ethnicity selection")
                            await asyncio.sleep(2)
                        
                        return True
                except Exception as e:
                    print(f"Failed to click element [{idx}]: {e}")
        except Exception as e:
            print(f"Failed to find ethnicity option: {e}")
        
        # If all else fails, try the brute-force approach
        print(f"Could not find ethnicity option: {target_ethnicity}")
        print("Falling back to hybrid vision/DOM model...")
        return await solve_page_with_hybrid_vision_dom(iframe, page)
            
    except Exception as e:
        print(f"An error occurred while handling Ethnicity page: {e}")
        print("Falling back to hybrid vision/DOM model...")
        return await solve_page_with_hybrid_vision_dom(iframe, page)

async def handle_children_page(iframe, page, persona):
    """
    Handle the children page.
    """
    try:
        print("Detected 'Children' page. Handling children information...")
        
        # Get children info from persona
        has_children = persona.get("about_you", {}).get("has_children", True)
        print(f"Persona has children: {has_children}")
        
        if has_children:
            # First, let's check what's currently on the page
            add_child_button = iframe.locator('button:has-text("+ Add Child")')
            month_inputs = iframe.locator('input[type="number"][placeholder="MM"]')
            male_labels = iframe.locator('label:has-text("Male")')
            
            current_children_count = await month_inputs.count()
            add_button_visible = await add_child_button.count() > 0
            male_labels_count = await male_labels.count()
            
            print(f"Current state: {current_children_count} children, Add button visible: {add_button_visible}, Male labels: {male_labels_count}")
            
            # If we have no children and the add button is visible, add 2 children
            if current_children_count == 0 and add_button_visible:
                print("No children detected, adding 2 children...")
                
                # Add first child
                await add_child_button.first.click()
                print("Added first child")
                await asyncio.sleep(2)
                
                # Update counts after adding
                current_children_count = await month_inputs.count()
                male_labels_count = await male_labels.count()
                print(f"After adding: {current_children_count} children, {male_labels_count} male labels")
            
            # If we have too many children, remove extras
            while current_children_count > 1:
                remove_buttons = iframe.locator('button:has-text("Remove")')
                if await remove_buttons.count() > 0:
                    print(f"Removing extra child (current: {current_children_count})")
                    await remove_buttons.last.click()
                    await asyncio.sleep(2)
                    current_children_count = await month_inputs.count()
                    print(f"After removal: {current_children_count} children")
                else:
                    break
            
            # Now fill in details for each child
            for child_index in range(min(current_children_count, 1)):
                print(f"Filling details for child {child_index + 1}...")
                
                # Fill month and year
                month_input = month_inputs.nth(child_index)
                year_input = iframe.locator('input[type="number"][placeholder="YYYY"]').nth(child_index)
                
                if await month_input.count() > 0:
                    month_value = "6" if child_index == 0 else "3"
                    await month_input.fill(month_value)
                    print(f"Filled child {child_index + 1} month: {month_value}")
                    await asyncio.sleep(1)
                
                if await year_input.count() > 0:
                    year_value = "2015" if child_index == 0 else "2018"
                    await year_input.fill(year_value)
                    print(f"Filled child {child_index + 1} year: {year_value}")
                    await asyncio.sleep(1)
                
                # Click Male label for this child
                male_label = male_labels.nth(child_index)
                if await male_label.count() > 0:
                    # Get the text content of the label to verify we're clicking the right one
                    label_text = await male_label.inner_text()
                    print(f"Clicking Male label for child {child_index + 1}, text: '{label_text}'")
                    
                    # Try clicking both the label and the associated input for better reliability
                    try:
                        await male_label.click()
                        print(f"Clicked Male label for child {child_index + 1}")
                        
                        # Also try clicking the associated radio button/checkbox if it exists
                        if child_index == 0:
                            # For first child, try clicking the first Male input
                            male_input = iframe.locator('input[type="radio"][value="m"], input[type="checkbox"][value="m"]').first
                        else:
                            # For second child, try clicking the second Male input
                            male_input = iframe.locator('input[type="radio"][value="m"], input[type="checkbox"][value="m"]').nth(1)
                        
                        if await male_input.count() > 0:
                            await male_input.click()
                            print(f"Also clicked Male input for child {child_index + 1}")
                        
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"Error clicking Male label for child {child_index + 1}: {e}")
                else:
                    print(f"Warning: Could not find Male label for child {child_index + 1}")
            
            # Now try to click the Confirm button
            # Try different confirm button patterns
            confirm_selectors = [
                f'button:has-text("Confirm ({current_children_count})")',
                'button:has-text("Confirm (1)")',
                'button:has-text("Confirm")',
                'button:has-text("Next")',
                'button:has-text("Continue")'
            ]
            
            for selector in confirm_selectors:
                confirm_button = iframe.locator(selector)
                if await confirm_button.count() > 0:
                    # Check if button is enabled
                    is_enabled = await confirm_button.first.is_enabled()
                    print(f"Found confirm button with selector: {selector}, enabled: {is_enabled}")
                    
                    if is_enabled:
                        await confirm_button.first.click()
                        print(f"Clicked confirm button using selector: {selector}")
                        await asyncio.sleep(2)
                        
                        # Check if we're still on the same page
                        page_text_after = await iframe.locator('body').text_content()
                        if "Children" in page_text_after and "Do you have or are expecting any children" in page_text_after:
                            print("Warning: Still on children page after clicking confirm button")
                            # Check for any validation messages
                            error_count = await iframe.locator('text=*error*').count()
                            required_count = await iframe.locator('text=*required*').count()
                            please_count = await iframe.locator('text=*please*').count()
                            validation_messages = error_count + required_count + please_count
                            print(f"Validation messages found: {validation_messages}")
                        else:
                            print("Successfully moved to next page")
                        
                        return True
                    else:
                        print(f"Confirm button found but disabled: {selector}")
                else:
                    print(f"Confirm button not found with selector: {selector}")
            
            print("Could not find any enabled confirm button")
            return False
            
        else:
            # Select "None/Not Expecting" option
            none_option = iframe.locator('label:has-text("None/Not Expecting")')
            if await none_option.count() > 0:
                await none_option.first.click()
                print("Selected 'None/Not Expecting' option")
                await asyncio.sleep(1)
                
                # Look for confirm button
                confirm_button = iframe.locator('button:has-text("Confirm")')
                if await confirm_button.count() > 0:
                    await confirm_button.first.click()
                    print("Clicked 'Confirm' button")
                    await asyncio.sleep(2)
                    return True
                else:
                    print("Could not find 'Confirm' button for None option")
                    return False
            else:
                print("Could not find 'None/Not Expecting' option")
                return False
                
    except Exception as e:
        print(f"Error in handle_children_page: {e}")
        return False

async def handle_children_confirmation_page(iframe, page, persona):
    """
    Handle the children confirmation page that appears after adding children.
    This page typically shows a summary of the children added and asks for confirmation.
    """
    try:
        print("Detected 'Children confirmation' page. Handling confirmation...")
        
        # Look for the confirm button with the count of children
        confirm_selectors = [
            'button:has-text("Confirm (2)")',
            'button:has-text("Confirm (3)")',
            'button:has-text("Confirm")',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Submit")'
        ]
        
        for selector in confirm_selectors:
            try:
                confirm_button = iframe.locator(selector)
                if await confirm_button.count() > 0:
                    await confirm_button.first.click()
                    print(f"Clicked confirm button using selector: {selector}")
                    await asyncio.sleep(2)
                    return True
            except Exception as e:
                print(f"Failed with selector {selector}: {e}")
                continue # This line needs to be indented by 4 spaces relative to 'except
            
        # If no confirm button found, try to find any clickable button
        try:
            any_button = iframe.locator('button').first
            if await any_button.count() > 0:
                button_text = await any_button.inner_text()
                await any_button.click()
                print(f"Clicked generic button with text: {button_text}")
                await asyncio.sleep(2)
                return True
        except Exception as e:
            print(f"Could not find any clickable button: {e}")
        
        print("Could not find confirmation button")
        return False
        
    except Exception as e:
        print(f"Error in handle_children_confirmation_page: {e}")
        return False

async def handle_job_title_page(iframe, page, persona):
    """
    Handle the job title selection page.
    """
    try:
        print("Detected 'Job title' page. Handling job title selection...")
        
        # Get job info from persona
        job_title = persona.get("work", {}).get("job_title", "Manager")
        print(f"Persona job title: {job_title}")
        
        # Map persona job title to survey options
        job_mapping = {
            "C-Level": "C-Level (e.g. CEO, CFO), Owner, Partner, President",
            "Vice President": "Vice President (EVP, SVP, AVP, VP)",
            "Director": "Director (Group Director, Sr. Director, Director)",
            "Manager": "Manager (Group Manager, Sr. Manager, Manager, Program Manager)",
            "Analyst": "Analyst",
            "Assistant": "Assistant or Associate",
            "Consultant": "Consultant",
            "Administrative": "Administrative (Clerical or Support Staff)",
            "Intern": "Intern",
            "Volunteer": "Volunteer"
        }
        
        # Default to Manager if job title not found
        target_job = job_mapping.get(job_title, "Manager (Group Manager, Sr. Manager, Manager, Program Manager)")
        print(f"Selecting job title: {target_job}")
        
        # Try to find and click the job title option
        try:
            job_selectors = [
                f'button:has-text("{target_job}")',
                f'label:has-text("{target_job}")',
                f'div:has-text("{target_job}")',
                # Try partial matches
                f'button:has-text("Manager")',
                f'label:has-text("Manager")',
                f'div:has-text("Manager")',
                f'button:has-text("Director")',
                f'label:has-text("Director")',
                f'div:has-text("Director")'
            ]
            
            for selector in job_selectors:
                try:
                    job_option = iframe.locator(selector)
                    if await job_option.count() > 0:
                        await job_option.first.click()
                        print(f"Clicked job title option using selector: {selector}")
                        await asyncio.sleep(2)
                        return True
                except Exception as e:
                    continue
            
            print(f"Could not find job title option: {target_job}")
            return False
        except Exception as e:
            print(f"Error selecting job title: {e}")
            return False
            
    except Exception as e:
        print(f"An error occurred while handling Job title page: {e}")
        return False

async def handle_company_employee_range_page(iframe, page, persona):
    """
    Handle the company employee range question.
    """
    try:
        print("Detected 'Company employee range' page. Handling employee range selection...")
        
        # Get company info from persona
        company_size = persona.get("work", {}).get("company_size", "101-500")
        print(f"Persona company size: {company_size}")
        
        # Map persona company size to survey options
        size_mapping = {
            "1": "1",
            "2-10": "2-10",
            "11-50": "11-50",
            "51-100": "51-100",
            "101-500": "101-500",
            "501-1000": "501-1000",
            "1001-5000": "1001-5000",
            "5000+": "5000 or more"
        }
        
        target_size = size_mapping.get(company_size, "101-500")
        print(f"Selecting company size: {target_size}")
        
        # Try to find and click the company size option
        try:
            size_selectors = [
                f'button:has-text("{target_size}")',
                f'label:has-text("{target_size}")',
                f'div:has-text("{target_size}")',
                # Try partial matches
                f'button:has-text("101-500")',
                f'label:has-text("101-500")',
                f'div:has-text("101-500")'
            ]
            
            for selector in size_selectors:
                try:
                    size_option = iframe.locator(selector)
                    if await size_option.count() > 0:
                        await size_option.first.click()
                        print(f"Clicked company size option using selector: {selector}")
                        await asyncio.sleep(2)
                        return True
                except Exception as e:
                    continue
            
            print(f"Could not find company size option: {target_size}")
            return False
        except Exception as e:
            print(f"Error selecting company size: {e}")
            return False
            
    except Exception as e:
        print(f"An error occurred while handling Company employee range page: {e}")
        return False

async def handle_company_industry_page(iframe, page, persona):
    """
    Handle the company industry selection page.
    """
    try:
        print("Detected 'Company industry' page. Handling industry selection...")
        
        # Get industry info from persona
        industry = persona.get("work", {}).get("industry", "Information Technology/IT")
        print(f"Persona industry: {industry}")
        
        # Map persona industry to survey options
        industry_mapping = {
            "Technology": "Information Technology/IT",
            "IT": "Information Technology/IT",
            "Software": "Computer Software",
            "Hardware": "Computer Hardware",
            "Internet": "Internet",
            "Telecommunications": "Telecommunications",
            "Finance": "Banking/Financial",
            "Insurance": "Insurance",
            "Accounting": "Accounting",
            "Communications": "Communications/Information",
            "Electronics": "Consumer Electronics",
            "Reseller": "Computer Reseller (software/hardware)"
        }
        
        target_industry = industry_mapping.get(industry, "Information Technology/IT")
        print(f"Selecting industry: {target_industry}")
        
        # Try to find and click the industry option
        try:
            industry_selectors = [
                f'button:has-text("{target_industry}")',
                f'label:has-text("{target_industry}")',
                f'div:has-text("{target_industry}")',
                # Try partial matches
                f'button:has-text("Information Technology")',
                f'label:has-text("Information Technology")',
                f'div:has-text("Information Technology")',
                f'button:has-text("Computer Software")',
                f'label:has-text("Computer Software")',
                f'div:has-text("Computer Software")'
            ]
            
            for selector in industry_selectors:
                try:
                    industry_option = iframe.locator(selector)
                    if await industry_option.count() > 0:
                        await industry_option.first.click()
                        print(f"Clicked industry option using selector: {selector}")
                        await asyncio.sleep(2)
                        return True
                except Exception as e:
                    continue
            
            print(f"Could not find industry option: {target_industry}")
            return False
        except Exception as e:
            print(f"Error selecting industry: {e}")
            return False
            
    except Exception as e:
        print(f"An error occurred while handling Company industry page: {e}")
        return False

async def handle_company_revenue_page(iframe, page, persona):
    """
    Handle the company revenue range question.
    """
    try:
        print("Detected 'Company revenue range' page. Handling revenue selection...")
        
        # Get revenue info from persona
        revenue = persona.get("work", {}).get("company_revenue", "$1 Million - $4.99 Million")
        print(f"Persona company revenue: {revenue}")
        
        # Map persona revenue to survey options
        revenue_mapping = {
            "Under $100,000": "Under $100,000",
            "$100,000 - $249,999": "$100,000 - $249,999",
            "$250,000 - $499,999": "$250,000 - $499,999",
            "$500,000 - $999,999": "$500,000 - $999,999",
            "$1 Million - $4.99 Million": "$1 Million - $4.99 Million",
            "$5 Million - $9.99 Million": "$5 Million - $9.99 Million",
            "$10 Million - $24.99 Million": "$10 Million - $24.99 Million",
            "$25 Million - $49.99 Million": "$25 Million - $49.99 Million",
            "$50 Million - $99.99 Million": "$50 Million - $99.99 Million",
            "$100 Million - $249.99 Million": "$100 Million - $249.99 Million",
            "$250 Million - $499.99 Million": "$250 Million - $499.99 Million",
            "$500 Million - $999.99 Million": "$500 Million - $999.99 Million",
            "$1 Billion+": "$1 Billion or more"
        }
        
        target_revenue = revenue_mapping.get(revenue, "$1 Million - $4.99 Million")
        print(f"Selecting revenue range: {target_revenue}")
        
        # Try to find and click the revenue option
        try:
            revenue_selectors = [
                f'button:has-text("{target_revenue}")',
                f'label:has-text("{target_revenue}")',
                f'div:has-text("{target_revenue}")',
                # Try partial matches
                f'button:has-text("$1 Million")',
                f'label:has-text("$1 Million")',
                f'div:has-text("$1 Million")'
            ]
            
            for selector in revenue_selectors:
                try:
                    revenue_option = iframe.locator(selector)
                    if await revenue_option.count() > 0:
                        await revenue_option.first.click()
                        print(f"Clicked revenue option using selector: {selector}")
                        await asyncio.sleep(2)
                        
                        # After clicking revenue, look for and click Next/Continue button
                        next_selectors = [
                            'button:has-text("Next")',
                            'button:has-text("Continue")', 
                            'button:has-text("Submit")',
                            'button:has-text("Confirm")',
                            'button:has-text("Proceed")',
                            'button:has-text("Save")'
                        ]
                        
                        for next_selector in next_selectors:
                            try:
                                next_button = iframe.locator(next_selector)
                                if await next_button.count() > 0:
                                    await next_button.first.click()
                                    print(f"Clicked next button using selector: {next_selector}")
                                    await asyncio.sleep(2)
                                    break
                            except Exception:
                                continue
                        
                        return True
                except Exception as e:
                    continue
            
            print(f"Could not find revenue option: {target_revenue}")
            return False
        except Exception as e:
            print(f"Error selecting revenue: {e}")
            return False
            
    except Exception as e:
        print(f"An error occurred while handling Company revenue page: {e}")
        return False

async def handle_company_department_page(iframe, page, persona):
    """
    Handle the company department selection page.
    """
    try:
        print("Detected 'Company department' page. Handling department selection...")
        
        # Get job title from persona to determine appropriate department
        job_title = persona.get("work", {}).get("job_title", "Senior Program Manager")
        print(f"Persona job title: {job_title}")
        
        # Map job title to appropriate department
        department_mapping = {
            "Senior Program Manager": "Operations",
            "Software Engineer": "Information Technology/IT", 
            "Product Manager": "Marketing",
            "Sales Manager": "Sales/Business Development",
            "Accountant": "Finance/Accounting",
            "HR Manager": "Human Resources",
            "Legal Counsel": "Legal/Law",
            "CEO": "Executive Leadership",
            "Customer Service Rep": "Customer Service/Client Service"
        }
        
        # Default to Operations for technical/management roles
        target_department = department_mapping.get(job_title, "Operations")
        print(f"Selecting department: {target_department}")
        
        # Try different selectors for the department options
        department_selectors = [
            f'label:has-text("{target_department}")',
            f'div:has-text("{target_department}")',
            f'[role="button"]:has-text("{target_department}")',
            f'button:has-text("{target_department}")'
        ]
        
        for selector in department_selectors:
            try:
                element = iframe.locator(selector)
                if await element.count() > 0:
                    await element.first.click()
                    print(f"Clicked department option using selector: {selector}")
                    await asyncio.sleep(2)
                    return True
            except Exception as e:
                print(f"Failed with selector {selector}: {e}")
                continue
        
        print(f"Could not find department option: {target_department}")
        print("Falling back to hybrid vision/DOM model...")
        return await solve_page_with_hybrid_vision_dom(iframe, page)
        
    except Exception as e:
        print(f"Error in handle_company_department_page: {e}")
        return False

async def handle_living_situation_page(iframe, page, persona):
    """
    Handle the living situation question.
    """
    try:
        print("Detected 'Living situation' page. Handling living situation selection...")
        
        # Get living situation from persona
        living_situation = persona.get("about_you", {}).get("living_situation", "Homeowner")
        print(f"Persona living situation: {living_situation}")
        
        # Map persona living situation to survey options
        situation_mapping = {
            "Renting": "Renting",
            "Homeowner": "Homeowner",
            "Other": "Other"
        }
        
        target_situation = situation_mapping.get(living_situation, "Homeowner")
        print(f"Selecting living situation: {target_situation}")
        
        # Try to find and click the living situation option
        try:
            situation_selectors = [
                f'button:has-text("{target_situation}")',
                f'label:has-text("{target_situation}")',
                f'div:has-text("{target_situation}")',
                # Try partial matches
                f'button:has-text("Homeowner")',
                f'label:has-text("Homeowner")',
                f'div:has-text("Homeowner")',
                f'button:has-text("Renting")',
                f'label:has-text("Renting")',
                f'div:has-text("Renting")'
            ]
            
            for selector in situation_selectors:
                try:
                    situation_option = iframe.locator(selector)
                    if await situation_option.count() > 0:
                        await situation_option.first.click()
                        print(f"Clicked living situation option using selector: {selector}")
                        await asyncio.sleep(2)
                        return True
                except Exception as e:
                    continue
            
            print(f"Could not find living situation option: {target_situation}")
            return False
        except Exception as e:
            print(f"Error selecting living situation: {e}")
            return False
            
    except Exception as e:
        print(f"An error occurred while handling Living situation page: {e}")
        return False

async def handle_smartphone_page(iframe, page, persona):
    """
    Handle the smartphone ownership question.
    """
    try:
        print("Detected 'Smartphone' page. Handling smartphone question...")
        
        # Get smartphone info from persona
        has_smartphone = persona.get("about_you", {}).get("has_smartphone", True)
        smartphone_use = persona.get("about_you", {}).get("smartphone_use", "personal")
        print(f"Persona has smartphone: {has_smartphone}, use: {smartphone_use}")
        
        if has_smartphone:
            # Map smartphone use to survey options
            use_mapping = {
                "business": "Yes, for business",
                "personal": "Yes, for personal",
                "both": "Yes, for both"
            }
            
            target_use = use_mapping.get(smartphone_use, "Yes, for personal")
            print(f"Selecting smartphone use: {target_use}")
            
            # Try to find and click the smartphone option
            try:
                smartphone_selectors = [
                    f'button:has-text("{target_use}")',
                    f'label:has-text("{target_use}")',
                    f'div:has-text("{target_use}")',
                    # Try partial matches
                    f'button:has-text("personal")',
                    f'label:has-text("personal")',
                    f'div:has-text("personal")',
                    f'button:has-text("business")',
                    f'label:has-text("business")',
                    f'div:has-text("business")',
                    f'button:has-text("both")',
                    f'label:has-text("both")',
                    f'div:has-text("both")'
                ]
                
                for selector in smartphone_selectors:
                    try:
                        smartphone_option = iframe.locator(selector)
                        if await smartphone_option.count() > 0:
                            await smartphone_option.first.click()
                            print(f"Clicked smartphone option using selector: {selector}")
                            await asyncio.sleep(2)
                            
                            # Check if this is the final page (100% completion) and look for Finish button
                            page_text = await iframe.locator('body').text_content()
                            if "100%" in page_text or "Finish" in page_text:
                                print("Detected final page, looking for Finish button...")
                                finish_selectors = [
                                    'button:has-text("Finish")',
                                    'button:has-text("Complete")',
                                    'button:has-text("Submit")',
                                    'button:has-text("Done")'
                                ]
                                
                                for finish_selector in finish_selectors:
                                    try:
                                        finish_button = iframe.locator(finish_selector)
                                        if await finish_button.count() > 0:
                                            await finish_button.first.click()
                                            print(f"Clicked finish button using selector: {finish_selector}")
                                            await asyncio.sleep(2)
                                            return "SURVEY_COMPLETE"
                                    except Exception as e:
                                        continue
                            
                            return True
                    except Exception as e:
                        continue
                
                print(f"Could not find smartphone option: {target_use}")
                return False
            except Exception as e:
                print(f"Error selecting smartphone option: {e}")
                return False
        else:
            # Click "I don't own a smartphone"
            try:
                no_smartphone_button = iframe.locator('button:has-text("I don\'t own a smartphone"), button:has-text("No smartphone"), button:has-text("No")')
                if await no_smartphone_button.count() > 0:
                    await no_smartphone_button.first.click()
                    print("Clicked 'I don't own a smartphone' button")
                    await asyncio.sleep(2)
                    return True
            except Exception as e:
                print(f"Could not find no smartphone button: {e}")
                return False
            
    except Exception as e:
        print(f"An error occurred while handling Smartphone page: {e}")
        return False

async def detect_and_fill_form_fields(iframe, persona):
    """
    Comprehensive form field detection and filling.
    Detects all form fields and fills them based on persona data.
    """
    print("Detecting all form fields...")
    
    # Common field patterns to look for
    field_patterns = [
        ("zipcode", "Zipcode", "zip", "postal"),
        ("city", "City", "town"),
        ("state", "State", "province"),
        ("address", "Address", "street", "mailing"),
        ("name", "Name", "full_name", "first_name", "last_name"),
        ("email", "Email", "e-mail"),
        ("phone", "Phone", "telephone", "mobile"),
        ("age", "Age", "birth_year"),
        ("gender", "Gender", "sex"),
        ("income", "Income", "salary", "earnings"),
        ("education", "Education", "school", "degree"),
        ("employment", "Employment", "job", "work")
    ]
    
    filled_fields = []
    
    for field_key, *patterns in field_patterns:
        for pattern in patterns:
            try:
                # Look for input fields with these patterns
                field = iframe.locator(f'input[placeholder*="{pattern}"], input[name*="{pattern}"], label:has-text("{pattern}") + input, input[aria-label*="{pattern}"]')
                
                if await field.count() > 0:
                    # Get the actual input element
                    input_element = field.first
                    
                    if await input_element.is_visible(timeout=1000):
                        # Determine if it's required (look for asterisk or required attribute)
                        is_required = await input_element.get_attribute("required") is not None
                        
                        # Fill based on field type and persona data
                        value = get_field_value_from_persona(field_key, persona)
                        if value:
                            await input_element.fill(value)
                            print(f"Filled {field_key}: {value} {'(required)' if is_required else '(optional)'}")
                            filled_fields.append(field_key)
                        elif is_required:
                            print(f"WARNING: Required field {field_key} not found in persona data")
                        
                        break  # Found this field, move to next
                        
            except Exception as e:
                continue  # Skip this pattern if it fails
    
    print(f"Detected and filled {len(filled_fields)} fields: {', '.join(filled_fields)}")
    return filled_fields

def get_field_value_from_persona(field_key, persona):
    """
    Extract field value from persona data based on field key.
    """
    field_mapping = {
        "zipcode": persona.get("about_you", {}).get("zipcode"),
        "city": persona.get("about_you", {}).get("city"),
        "state": persona.get("about_you", {}).get("state"),
        "name": persona.get("about_you", {}).get("full_name"),
        "email": persona.get("about_you", {}).get("email"),
        "age": str(persona.get("about_you", {}).get("age", "")),
        "gender": persona.get("about_you", {}).get("gender"),
        "income": persona.get("work", {}).get("personal_income_before_taxes"),
        "education": "Graduated 4 year college/University",  # Default from persona
        "employment": persona.get("work", {}).get("employment_status"),
        "address": f"123 Main St, {persona.get('about_you', {}).get('city', 'Los Angeles')}, {persona.get('about_you', {}).get('state', 'California')} {persona.get('about_you', {}).get('zipcode', '90001')}"
    }
    
    return field_mapping.get(field_key)

async def try_auto_start_survey(page, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            print(f"[Auto-Start] Attempt {attempt+1} to start a survey...")
            
            # Wait for survey elements to be visible
            await page.wait_for_selector('button:has-text("Start"), a[href*="survey"], .survey-card, [data-testid*="survey"]', state='visible', timeout=10000)
            
            # Try multiple selectors to find survey elements
            selectors_to_try = [
                'button:has-text("Start")',
                'a[href*="survey"]',
                '.survey-card',
                '[data-testid*="survey"]',
                'button:has-text("Start earning")',  # Keep as fallback
                'a.survey-card'
            ]
            
            for selector in selectors_to_try:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    if count > 0:
                        # Get the first visible element
                        for i in range(count):
                            element = elements.nth(i)
                            if await element.is_visible():
                                await element.click()
                                print(f"[Auto-Start] Clicked survey element using selector: {selector}")
                                return True
                except Exception as e:
                    print(f"[Auto-Start] Selector {selector} failed: {e}")
                    continue
            
            # If no specific selectors work, try to find any clickable survey-like element
            try:
                # Look for elements with survey-related text or attributes
                survey_elements = page.locator('button, a').filter(has_text=re.compile(r'start|survey|earn', re.IGNORECASE))
                count = await survey_elements.count()
                if count > 0:
                    for i in range(count):
                        element = survey_elements.nth(i)
                        if await element.is_visible():
                            await element.click()
                            print("[Auto-Start] Clicked survey element using text-based selector.")
                            return True
            except Exception as e:
                print(f"[Auto-Start] Text-based selector failed: {e}")
                
        except Exception as e:
            print(f"[Auto-Start] Attempt {attempt+1} failed: {e}")
        await asyncio.sleep(2)
    print("[Auto-Start] All attempts failed. Please navigate manually and press Enter.")
    input("Press Enter once you are on a survey page...")
    return False

async def page_router(page):
    print("Routing page...")
    iframe_locator = page.frame_locator('iframe[title="signup-survey"]')
    try:
        await iframe_locator.locator('body').wait_for(timeout=10000)
        
        # Get page text for detection
        page_text = await iframe_locator.locator('body').inner_text()
        page_text_lower = page_text.lower()
        
        # Debug: Print first 200 characters of page text
        print(f"[DEBUG] Page text preview: {page_text[:200]}...")
        
        # Debug: Check for children page keywords
        print(f"[DEBUG] 'children' in text: {'children' in page_text_lower}")
        print(f"[DEBUG] 'under the age of 18' in text: {'under the age of 18' in page_text_lower}")
        print(f"[DEBUG] 'expecting' in text: {'expecting' in page_text_lower}")
        
        # Check for Children page FIRST (before Date of Birth detection)
        if "children" in page_text_lower and ("under the age of 18" in page_text_lower or "expecting" in page_text_lower):
            print("[DEBUG] Detected Children page")
            return await handle_children_page(iframe_locator, page, PERSONA)
        
        # Debug: Check why children page detection might be failing
        elif "children" in page_text_lower:
            print(f"[DEBUG] Found 'children' in page text but missing other keywords")
            print(f"[DEBUG] 'under the age of 18' in text: {'under the age of 18' in page_text_lower}")
            print(f"[DEBUG] 'expecting' in text: {'expecting' in page_text_lower}")
            print(f"[DEBUG] Full page text: {page_text}")
            return await handle_children_page(iframe_locator, page, PERSONA)
        
        # Check for Date of Birth page
        elif (await iframe_locator.get_by_placeholder("MM").is_visible(timeout=2000) and
            await iframe_locator.get_by_placeholder("DD").is_visible(timeout=2000) and
            await iframe_locator.get_by_placeholder("YYYY").is_visible(timeout=2000)):
            print("[DEBUG] Detected Date of Birth page")
            return await handle_date_of_birth_page(iframe_locator, page, PERSONA)
        
        # Check for Address page (either initial consent page or full address form)
        elif (await iframe_locator.get_by_placeholder("Zipcode").is_visible(timeout=2000)):
            print("[DEBUG] Detected Address page")
            return await handle_address_page(iframe_locator, page, PERSONA)
        
        # Check for Ethnicity page (look for ethnicity-related text)
        elif ("accurate matching" in page_text_lower or 
              "ethnicity" in page_text_lower or
              "white/caucasian" in page_text_lower or
              "black or african-american" in page_text_lower or
              "asian american" in page_text_lower):
            print("[DEBUG] Detected Ethnicity page")
            return await handle_ethnicity_page(iframe_locator, page, PERSONA)
        
        # Check for Children confirmation page (after adding children)
        elif "confirm (2)" in page_text_lower and "children" in page_text_lower:
            print("[DEBUG] Detected Children confirmation page")
            return await handle_children_confirmation_page(iframe_locator, page, PERSONA)
        
        # Check for Job title page
        elif "job title" in page_text_lower and "level of responsibility" in page_text_lower:
            print("[DEBUG] Detected Job title page")
            return await handle_job_title_page(iframe_locator, page, PERSONA)
        
        # Check for Company employee range page
        elif "company employee range" in page_text_lower and "employees work at your organization" in page_text_lower:
            print("[DEBUG] Detected Company employee range page")
            return await handle_company_employee_range_page(iframe_locator, page, PERSONA)
        
        # Check for Company industry page
        elif "company industry" in page_text_lower and "primary industry" in page_text_lower:
            print("[DEBUG] Detected Company industry page")
            return await handle_company_industry_page(iframe_locator, page, PERSONA)
        
        # Check for Company revenue range page
        elif "company revenue range" in page_text_lower and "annual revenue" in page_text_lower:
            print("[DEBUG] Detected Company revenue range page")
            return await handle_company_revenue_page(iframe_locator, page, PERSONA)
        
        # Check for Company department page
        elif "company department" in page_text_lower and ("primarily work" in page_text_lower or "department" in page_text_lower):
            print("[DEBUG] Detected Company department page")
            return await handle_company_department_page(iframe_locator, page, PERSONA)
        
        # Check for Living situation page
        elif "living situation" in page_text_lower and "current living situation" in page_text_lower:
            print("[DEBUG] Detected Living situation page")
            return await handle_living_situation_page(iframe_locator, page, PERSONA)
        
        # Check for Smartphone page
        elif "smart phone" in page_text_lower or "smartphone" in page_text_lower:
            print("[DEBUG] Detected Smartphone page")
            return await handle_smartphone_page(iframe_locator, page, PERSONA)
        
        # Check for consent forms
        elif await iframe_locator.locator('button:has-text("Agree"), button:has-text("Consent"), a:has-text("Agree"), a:has-text("Consent"), button:has-text("Agree and Continue")').count() > 0:
            print("[DEBUG] Detected consent form, handling automatically")
            try:
                # Try to find and click the agree/consent button with multiple selectors
                selectors = [
                    'button:has-text("Agree and Continue")',
                    'button:has-text("Agree")',
                    'button:has-text("Consent")',
                    'a:has-text("Agree")',
                    'a:has-text("Consent")',
                    'input[type="submit"][value*="Agree"]',
                    'input[type="button"][value*="Agree"]'
                ]
                
                for selector in selectors:
                    try:
                        agree_button = iframe_locator.locator(selector).first
                        if await agree_button.is_visible():
                            await agree_button.click()
                            print(f"Clicked agree/consent button using selector: {selector}")
                            return True
                    except Exception as e:
                        continue
                
                print("No visible agree button found, using hybrid approach")
                return await solve_page_with_hybrid_vision_dom(iframe_locator, page)
            except Exception as e:
                print(f"Error clicking consent button: {e}")
                return await solve_page_with_hybrid_vision_dom(iframe_locator, page)
        
        # Check for text input pages (open-ended questions)
        elif await iframe_locator.locator('input[type="text"], textarea').count() > 0:
            print("[DEBUG] Detected page with text input, using hybrid vision/DOM model")
            return await solve_page_with_hybrid_vision_dom(iframe_locator, page)
        
        # Check for any page with radio buttons or checkboxes that we haven't specifically handled
        elif await iframe_locator.locator('input[type="radio"], input[type="checkbox"]').count() > 0:
            print("[DEBUG] Detected page with radio/checkbox inputs, using hybrid vision/DOM model")
            return await solve_page_with_hybrid_vision_dom(iframe_locator, page)
        
        # Check for survey completion indicators (more specific)
        elif any(completion_indicator in page_text_lower for completion_indicator in [
            "you have completed the survey", "survey has been completed", "thank you for completing", 
            "survey submission successful", "your responses have been recorded", "survey complete!",
            "congratulations! you have finished", "thank you for your participation"
        ]):
            print("Survey appears to be complete!")
            return "SURVEY_COMPLETE"
        
        # Check for URL-based completion indicators
        elif "thank" in page.url.lower() or "complete" in page.url.lower() or "finish" in page.url.lower():
            print("Survey completion detected via URL change!")
            return "SURVEY_COMPLETE"
        
        else:
            print("[DEBUG] No specific page detected, using hybrid vision/DOM model")
            return await solve_page_with_hybrid_vision_dom(iframe_locator, page)
    except Exception as e:
        print(f"[DEBUG] Exception in page_router: {e}")
        return await solve_page_with_hybrid_vision_dom(page, page)


def launch_options(*, headless=None):
    options = {"headless": Config.HEADLESS if headless is None else headless, "slow_mo": Config.SLOW_MO}
    executable = Config.BROWSER_EXECUTABLE
    if not executable and Config.BROWSER_NAME == "chromium":
        executable = shutil.which("chromium") or shutil.which("chromium-browser")
    if executable:
        options["executable_path"] = executable
    return options


async def main():
    if model is None:
        print("Set GOOGLE_API_KEY or GEMINI_API_KEY before starting a live session.")
        return False
    if not Config.AUTH_FILE.is_file():
        print("Authentication state is missing. Run python save_auth.py on your own computer first.")
        return False
    load_persona()
    if not Config.HEADLESS and os.name != "nt" and not os.environ.get("DISPLAY"):
        print("No graphical display is available. Use --headless, or run locally with a visible browser.")
        return False

    async with async_playwright() as playwright:
        browser_type = getattr(playwright, Config.BROWSER_NAME)
        browser = await browser_type.launch(**launch_options())
        context = None
        completed = False
        try:
            context = await browser.new_context(storage_state=str(Config.AUTH_FILE))
            page = await context.new_page()
            await page.goto(Config.SURVEY_URL, timeout=Config.PAGE_TIMEOUT)
            if not await try_auto_start_survey(page):
                if Config.HEADLESS:
                    print("No survey was started. Open the survey in a local visible browser first.")
                    return False
                await asyncio.to_thread(input, "Navigate to your survey, then press Enter to continue: ")
            previous_url = None
            failures = 0
            for attempt in range(50):
                await page.wait_for_load_state("domcontentloaded", timeout=Config.PAGE_TIMEOUT)
                failures = failures + 1 if page.url == previous_url else 0
                previous_url = page.url
                if failures >= 30:
                    print("Stopped: the survey page is not progressing.")
                    break
                result = await page_router(page)
                if result == "SURVEY_COMPLETE":
                    completed = True
                    break
                if result is False:
                    print("No verified action was available; stopping for user review.")
                    break
                await asyncio.sleep(3)
            return completed
        finally:
            if context is not None:
                await context.close()
            await browser.close()
            if model is not None and hasattr(model, "close"):
                await model.close()


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
