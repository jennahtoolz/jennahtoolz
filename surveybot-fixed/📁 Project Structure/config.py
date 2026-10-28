import os
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def local_path(name, default):
    value = Path(os.getenv(name, str(ROOT / default))).expanduser()
    return value.resolve() if value.is_absolute() else (ROOT / value).resolve()


class Config:
    """Configuration management for survey automation"""
    
    # API Keys
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY", "")
    CAPTCHA_API_URL = os.getenv("CAPTCHA_API_URL", "")
    CAPTCHA_API_SECRET = os.getenv("CAPTCHA_API_SECRET", "")
    
    # Proxy Settings
    PROXY_HOST = os.getenv("PROXY_HOST", "")
    PROXY_PORT = os.getenv("PROXY_PORT", "")
    PROXY_USER = os.getenv("PROXY_USER", "")
    PROXY_PASS = os.getenv("PROXY_PASS", "")
    
    # Browser Settings
    BROWSER_TYPE = os.getenv("BROWSER_TYPE", "playwright")  # playwright, selenium, undetected, hybrid
    HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
    SLOW_MO = int(os.getenv("SLOW_MO", "10"))
    
    # Survey Platform Settings
    SURVEY_PLATFORM = os.getenv("SURVEY_PLATFORM", "qmee")  # qmee, earnhaus, prolific, etc.
    SURVEY_URL = os.getenv("SURVEY_URL", "https://www.qmee.com/en-us/surveys")
    
    BROWSER_NAME = os.getenv("BROWSER_NAME", "chromium")
    BROWSER_EXECUTABLE = os.getenv("BROWSER_EXECUTABLE", "")
    AUTH_FILE = local_path("SURVEY_AUTH_FILE", "auth.json")
    PERSONA_FILE = local_path("SURVEY_PERSONA_FILE", "persona.json")

    # AI Settings
    AI_MODEL = os.getenv("AI_MODEL", "gemini-flash-latest")
    USE_VISION = os.getenv("USE_VISION", "true").lower() == "true"
    USE_FALLBACK = os.getenv("USE_FALLBACK", "true").lower() == "true"
    
    # Self-Operating Computer Settings
    USE_SELF_OPERATING_COMPUTER = os.getenv("USE_SELF_OPERATING_COMPUTER", "true").lower() == "true"
    VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4-vision-preview")
    USE_MOUSE_CONTROL = os.getenv("USE_MOUSE_CONTROL", "true").lower() == "true"
    SOC_HEADLESS = os.getenv("SOC_HEADLESS", "false").lower() == "true"
    SOC_DEBUG = os.getenv("SOC_DEBUG", "true").lower() == "true"
    
    # Personality Settings
    PERSONALITY_STYLE = os.getenv("PERSONALITY_STYLE", "discord_casual")
    MAX_SURVEYS = int(os.getenv("MAX_SURVEYS", "10"))
    DELAY_BETWEEN_ACTIONS = (float(os.getenv("MIN_DELAY", "1.0")), float(os.getenv("MAX_DELAY", "3.0")))
    
    # Timing Settings
    PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "30000"))
    ELEMENT_TIMEOUT = int(os.getenv("ELEMENT_TIMEOUT", "10000"))
    SURVEY_TIMEOUT = int(os.getenv("SURVEY_TIMEOUT", "300000"))  # 5 minutes
    
    # Retry Settings
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
    
    # Proxy Rotation Settings
    ROTATE_PROXY_ON_FAILURE = os.getenv("ROTATE_PROXY_ON_FAILURE", "true").lower() == "true"
    PROXY_ROTATION_INTERVAL = int(os.getenv("PROXY_ROTATION_INTERVAL", "10"))  # surveys
    
    # Stealth Settings
    RANDOM_DELAYS = os.getenv("RANDOM_DELAYS", "true").lower() == "true"
    MIN_DELAY = float(os.getenv("MIN_DELAY", "1.0"))
    MAX_DELAY = float(os.getenv("MAX_DELAY", "3.0"))
    
    # User Agent Settings
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0"
    ]
    
    # Survey Completion Indicators
    COMPLETION_INDICATORS = [
        "survey complete", "thank you", "congratulations", 
        "survey finished", "completion", "success", "100%",
        "survey submission successful", "your responses have been recorded"
    ]
    
    # Common Survey Elements
    SURVEY_ELEMENTS = {
        "start_buttons": [
            'button:has-text("Start")',
            'a[href*="survey"]',
            '.survey-card',
            '[data-testid*="survey"]',
            'button:has-text("Start earning")'
        ],
        "next_buttons": [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Submit")',
            'button:has-text("Proceed")',
            'input[type="submit"]'
        ],
        "agree_buttons": [
            'button:has-text("Agree")',
            'button:has-text("Consent")',
            'button:has-text("Yes")',
            'button:has-text("I agree")',
            'button:has-text("Accept")'
        ],
        "text_inputs": [
            'input[type="text"]',
            'textarea',
            'input[type="email"]',
            'input[type="number"]'
        ]
    }
    
    @classmethod
    def get_browser_config(cls) -> Dict[str, Any]:
        """Get browser configuration based on type"""
        config = {
            "headless": cls.HEADLESS,
            "slow_mo": cls.SLOW_MO,
            "timeout": cls.PAGE_TIMEOUT
        }
        
        if cls.BROWSER_TYPE == "selenium":
            config.update({
                "options": {
                    "--no-sandbox": True,
                    "--disable-dev-shm-usage": True,
                    "--disable-blink-features=AutomationControlled": True,
                    "--user-agent": cls.get_random_user_agent()
                }
            })
        elif cls.BROWSER_TYPE == "undetected":
            config.update({
                "undetectable_agent": True,
                "captcha_api_key": cls.CAPTCHA_API_KEY,
                "proxy_config": cls.get_proxy_config()
            })
        
        return config
    
    @classmethod
    def get_proxy_config(cls) -> Dict[str, Any]:
        """Get proxy configuration"""
        if cls.PROXY_HOST and cls.PROXY_PORT:
            return {
                "proxy_host": cls.PROXY_HOST,
                "proxy_port": int(cls.PROXY_PORT),
                "proxy_user": cls.PROXY_USER,
                "proxy_pass": cls.PROXY_PASS
            }
        return {}
    
    @classmethod
    def get_random_user_agent(cls) -> str:
        """Get a random user agent"""
        import random
        return random.choice(cls.USER_AGENTS)
    
    @classmethod
    def get_random_delay(cls) -> float:
        """Get a random delay for stealth"""
        import random
        if cls.RANDOM_DELAYS:
            return random.uniform(cls.MIN_DELAY, cls.MAX_DELAY)
        return cls.MIN_DELAY
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate the configuration"""
        errors = []
        
        if not cls.GOOGLE_API_KEY:
            errors.append("GOOGLE_API_KEY not set")
        
        if cls.BROWSER_TYPE not in ["playwright", "selenium", "undetected", "v2ray", "proxychains", "hybrid"]:
            errors.append(f"Invalid BROWSER_TYPE: {cls.BROWSER_TYPE}")
        
        if cls.SURVEY_PLATFORM not in ["qmee", "earnhaus", "prolific", "mturk"]:
            errors.append(f"Invalid SURVEY_PLATFORM: {cls.SURVEY_PLATFORM}")
        
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    @classmethod
    def print_config(cls):
        """Print current configuration"""
        print("Current Configuration:")
        print(f"  Browser Type: {cls.BROWSER_TYPE}")
        print(f"  Browser Engine: {cls.BROWSER_NAME}")
        print(f"  AI Model: {cls.AI_MODEL}")
        print(f"  Authentication File Present: {cls.AUTH_FILE.is_file()}")
        print(f"  Persona File Present: {cls.PERSONA_FILE.is_file()}")
        print(f"  Survey Platform: {cls.SURVEY_PLATFORM}")
        print(f"  Headless: {cls.HEADLESS}")
        print(f"  Use Vision: {cls.USE_VISION}")
        print(f"  Use Fallback: {cls.USE_FALLBACK}")
        print(f"  Proxy Rotation: {cls.ROTATE_PROXY_ON_FAILURE}")
        print(f"  Random Delays: {cls.RANDOM_DELAYS}")
        print(f"  API Key Set: {'Yes' if cls.GOOGLE_API_KEY else 'No'}")

# Create a sample .env file if it doesn't exist
def create_sample_env():
    """Create a sample .env file with configuration options"""
    env_content = """# API Keys
GOOGLE_API_KEY=
CAPTCHA_API_KEY=your_captcha_api_key_here
CAPTCHA_API_URL=https://api.captcha.com
CAPTCHA_API_SECRET=your_captcha_secret_here

# Proxy Settings
PROXY_HOST=
PROXY_PORT=
PROXY_USER=
PROXY_PASS=

# Browser Settings
BROWSER_TYPE=playwright
HEADLESS=false
SLOW_MO=10

# Survey Platform Settings
SURVEY_PLATFORM=qmee
SURVEY_URL=https://www.qmee.com/en-us/surveys

# AI Settings
AI_MODEL=gemini-1.5-flash-latest
USE_VISION=true
USE_FALLBACK=true

# Timing Settings
PAGE_TIMEOUT=30000
ELEMENT_TIMEOUT=10000
SURVEY_TIMEOUT=300000

# Retry Settings
MAX_RETRIES=3
RETRY_DELAY=5

# Proxy Rotation Settings
ROTATE_PROXY_ON_FAILURE=true
PROXY_ROTATION_INTERVAL=10

# Stealth Settings
RANDOM_DELAYS=true
MIN_DELAY=1.0
MAX_DELAY=3.0
"""
    
    if not (ROOT / ".env").exists():
        with (ROOT / ".env").open("x", encoding="utf-8") as f:
            f.write(env_content)
        print("Created sample .env file. Please update with your actual values.")

if __name__ == "__main__":
    create_sample_env()
    Config.print_config()
    if Config.validate_config():
        print("Configuration is valid!")
    else:
        print("Configuration has errors!")
