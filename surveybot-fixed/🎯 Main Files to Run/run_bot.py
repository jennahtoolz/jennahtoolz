#!/usr/bin/env python3
"""SurveyBot launcher with explicit setup, diagnostics and offline browser checks."""
import argparse
import asyncio
import importlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "📁 Project Structure"
sys.path.insert(0, str(PROJECT))
IMPLEMENTATIONS = ("playwright", "selenium", "undetected", "v2ray", "proxychains", "hybrid")


def parser():
    result = argparse.ArgumentParser(description="SurveyBot: browser startup and survey workflow")
    result.add_argument("--implementation", "-i", choices=IMPLEMENTATIONS, default=None)
    result.add_argument("--platform", "-p", choices=("qmee", "earnhaus", "prolific", "mturk"), default=None)
    visibility = result.add_mutually_exclusive_group()
    visibility.add_argument("--headless", action="store_true", dest="headless")
    visibility.add_argument("--headed", action="store_false", dest="headless")
    result.set_defaults(headless=None)
    result.add_argument("--browser", choices=("chromium", "firefox", "webkit"))
    result.add_argument("--executable", help="Existing browser executable; optional")
    result.add_argument("--url", help="Override the configured survey URL")
    result.add_argument("--config", action="store_true", help="Show configuration presence; never credential values")
    result.add_argument("--setup", action="store_true", help="Create .venv and install supported dependencies")
    result.add_argument("--smoke-test", action="store_true", help="Run only a local fixture with simulated AI; no accounts or API key needed")
    result.add_argument("--test-proxies", action="store_true", help="Run the optional legacy proxy check")
    result.add_argument("--proxy", action="store_true", help="Legacy proxy option")
    return result


def check_dependencies(implementation):
    modules = {
        "playwright": ("playwright.async_api", "google.genai", "dotenv"),
        "hybrid": ("playwright.async_api", "google.genai", "dotenv"),
        "selenium": ("selenium", "dotenv"),
        "undetected": ("undetected_chromedriver", "dotenv"),
        "v2ray": ("undetected_chromedriver", "dotenv"),
        "proxychains": ("undetected_chromedriver", "dotenv"),
    }
    missing = []
    for name in modules[implementation]:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        print("Missing dependencies for " + implementation + ": " + ", ".join(missing))
        print("Run: python setup.py (Playwright), or install the legacy requirements for other implementations.")
    return not missing


def main(argv=None):
    args = parser().parse_args(argv)
    if args.setup:
        return subprocess.call([sys.executable, str(ROOT / "setup.py")], cwd=ROOT)
    try:
        from config import Config
    except ImportError:
        print("Dependencies are not installed. Run python setup.py first.")
        return 2
    args.implementation = args.implementation or Config.BROWSER_TYPE
    args.platform = args.platform or Config.SURVEY_PLATFORM
    if args.implementation not in IMPLEMENTATIONS:
        print("Invalid BROWSER_TYPE. Choose a supported implementation.")
        return 2
    Config.BROWSER_TYPE = args.implementation
    Config.SURVEY_PLATFORM = args.platform
    if args.headless is not None:
        Config.HEADLESS = args.headless
    if args.browser:
        Config.BROWSER_NAME = args.browser
    if args.executable:
        Config.BROWSER_EXECUTABLE = args.executable
    if args.url:
        Config.SURVEY_URL = args.url
    if args.config:
        Config.print_config()
        return 0
    if not check_dependencies("playwright" if args.smoke_test else args.implementation):
        return 2
    if args.smoke_test:
        from browser_smoke import run_smoke_test
        return asyncio.run(run_smoke_test())
    if args.test_proxies:
        test_proxies()
        return 0
    if not Config.validate_config():
        return 2
    if args.implementation == "playwright":
        for path, hint in [(Config.PERSONA_FILE, "Create persona.json with your own profile facts."),
                           (Config.AUTH_FILE, "Run python save_auth.py locally to sign in with your own browser.")]:
            if not path.is_file():
                print(f"Required local file is missing: {path.name}. {hint}")
                return 2
    try:
        return run_bot(args)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        print(f"Startup failed ({type(error).__name__}). Check the selected implementation's dependencies and local files.")
        return 1


def run_bot(args):
    modules = {
        "playwright": ("survey_bot_playwright", "main"),
        "selenium": ("survey_bot_selenium", "main"),
        "undetected": ("survey_bot_undetected", "main"),
        "v2ray": ("survey_bot_v2ray", "V2RayEnhancedSurveyBot"),
        "proxychains": ("survey_bot_proxychains", "ProxychainsSurveyBot"),
        "hybrid": ("survey_bot_hybrid", "main"),
    }
    name, entry = modules[args.implementation]
    module = importlib.import_module("bot_implementations." + name)
    target = getattr(module, entry)
    if entry.endswith("SurveyBot"):
        result = target().run()
    else:
        result = target()
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return 1 if result is False else 0


def test_proxies():
    """Test and save working proxies"""
    print("Testing proxies...")
    
    try:
        from proxy_management.proxy_manager_v2ray import V2RayProxyManager
        
        manager = V2RayProxyManager(v2ray_path="./v2ray/v2ray")
        
        # Try to load from different config files
        config_files = [
            "configs/shadow_proxy_configs.json",
            "configs/v2ray_proxies.json",
            "configs/sample_v2ray_proxies.json"
        ]
        
        config_loaded = False
        for config_file in config_files:
            if os.path.exists(config_file):
                print(f"Loading proxies from {config_file}...")
                if manager.load_configs_from_file(config_file):
                    config_loaded = True
                    print(f"✓ Loaded {len(manager.proxy_configs)} proxy configurations")
                    break
        
        if not config_loaded:
            print("No proxy configuration files found. Creating sample configurations...")
            from proxy_management.proxy_manager_v2ray import create_sample_proxies
            create_sample_proxies()
            manager.load_configs_from_file("sample_v2ray_proxies.json")
        
        if manager.proxy_configs:
            print(f"\nTesting {len(manager.proxy_configs)} proxy configurations...")
            
            working_configs = []
            for i, config in enumerate(manager.proxy_configs):
                print(f"\nTesting proxy {i+1}/{len(manager.proxy_configs)}: {config.name}")
                print(f"  Protocol: {config.protocol}")
                print(f"  Address: {config.address}:{config.port}")
                print(f"  Security: {config.security}")
                print(f"  Network: {config.network}")
                
                success, response_time = manager.test_proxy(config, timeout=15)
                
                if success:
                    print(f"  ✓ Working - Response time: {response_time:.2f}s")
                    working_configs.append(config)
                else:
                    print(f"  ✗ Failed")
            
            print(f"\nSummary: {len(working_configs)}/{len(manager.proxy_configs)} proxies are working")
            
            # Save working configurations
            if working_configs:
                manager.proxy_configs = working_configs
                manager.save_configs_to_file("configs/working_proxies.json")
                print(f"\nSaved {len(working_configs)} working proxy configurations to configs/working_proxies.json")
            else:
                print("\nNo working proxies found. You may need to check your V2Ray installation or network connectivity.")
        else:
            print("No proxies available for testing")
            
    except ImportError as e:
        print(f"Proxy manager not available: {e}")
        print("Make sure the proxy_management module is properly installed.")
    except Exception as e:
        print(f"Error testing proxies: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Stopped by user.")
        sys.exit(130)
