# actions.py

async def click_element(page, element_id, element_map):
    """Clicks a specified element from the element map."""
    element_to_click = element_map.get(element_id)
    if not element_to_click:
        raise ValueError(f"Element with ID {element_id} not found in the element map.")
    
    action_text = (await element_to_click.inner_text() or "").strip()
    print(f"Toolbox: Clicking element [{element_id}] with text '{action_text}'")
    await element_to_click.click(timeout=15000)
    return f"Successfully clicked element {element_id}."

async def fill_textbox(page, element_id, text_to_fill, element_map):
    """Fills a specified textbox element with the given text."""
    element_to_fill = element_map.get(element_id)
    if not element_to_fill:
        raise ValueError(f"Element with ID {element_id} not found in the element map.")
    
    print(f"Toolbox: Filling element [{element_id}] with text '{text_to_fill}'")
    await element_to_fill.fill(text_to_fill)
    return f"Successfully filled element {element_id}."

# Add other actions here as needed