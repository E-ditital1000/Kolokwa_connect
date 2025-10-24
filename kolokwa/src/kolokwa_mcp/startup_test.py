#!/usr/bin/env python
"""
MCP Server Diagnostic and Startup Script
Tests configuration and starts servers with proper error handling
"""

import os
import sys
import subprocess
from pathlib import Path
import time
import requests

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor} (3.10+ required)")
        return False

def check_virtual_env():
    """Check if running in virtual environment"""
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print_success(f"Virtual environment active: {sys.prefix}")
        return True
    else:
        print_warning("Not running in virtual environment")
        return False

def check_django_setup():
    """Check if Django is properly configured"""
    try:
        import django
        from django.conf import settings
        
        # Try to access settings
        db_engine = settings.DATABASES['default']['ENGINE']
        print_success(f"Django configured: {django.get_version()}")
        print_info(f"Database: {db_engine}")
        return True
    except ImportError:
        print_error("Django not installed")
        return False
    except Exception as e:
        print_error(f"Django configuration error: {e}")
        return False

def check_required_packages():
    """Check if required packages are installed"""
    required = {
        'fastmcp': 'FastMCP',
        'workos': 'WorkOS',
        'redis': 'Redis (optional)',
        'uvicorn': 'Uvicorn',
        'django': 'Django'
    }
    
    all_ok = True
    for package, name in required.items():
        try:
            __import__(package)
            print_success(f"{name} installed")
        except ImportError:
            if package in ['redis', 'workos']:
                print_warning(f"{name} not installed (optional)")
            else:
                print_error(f"{name} not installed")
                all_ok = False
    
    return all_ok

def check_env_file():
    """Check if .env file exists and has required settings"""
    env_path = Path.cwd()
    while env_path != env_path.parent:
        env_file = env_path / '.env'
        if env_file.exists():
            print_success(f".env file found: {env_file}")
            
            # Check critical settings
            with open(env_file, 'r') as f:
                content = f.read()
                
            checks = {
                'MCP_AUTH_ENABLED': 'False',
                'CACHE_ENABLED': 'False',
                'ENVIRONMENT': 'development',
            }
            
            for key, expected in checks.items():
                if key in content:
                    if expected in content:
                        print_success(f"  {key}={expected}")
                    else:
                        print_warning(f"  {key} found but may not be set to {expected}")
                else:
                    print_warning(f"  {key} not found in .env")
            
            return True
        env_path = env_path.parent
    
    print_error(".env file not found")
    return False

def check_database_connection():
    """Test database connection"""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')
        import django
        django.setup()
        
        from dictionary.models import KoloquaEntry
        count = KoloquaEntry.objects.count()
        print_success(f"Database connected ({count} entries)")
        return True
    except Exception as e:
        print_error(f"Database connection failed: {e}")
        return False

def test_server_endpoint(port, server_name):
    """Test if server is responding"""
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=5)
        if response.status_code == 200:
            print_success(f"{server_name} (port {port}) is responding")
            return True
        else:
            print_warning(f"{server_name} responded with status {response.status_code}")
            return False
    except requests.ConnectionError:
        print_error(f"{server_name} (port {port}) not responding")
        return False
    except Exception as e:
        print_error(f"{server_name} test failed: {e}")
        return False

def main():
    """Main diagnostic routine"""
    print_header("KOLOKWA MCP SERVER DIAGNOSTIC")
    
    # System checks
    print_header("System Checks")
    py_ok = check_python_version()
    venv_ok = check_virtual_env()
    
    # Package checks
    print_header("Package Checks")
    pkg_ok = check_required_packages()
    
    # Configuration checks
    print_header("Configuration Checks")
    env_ok = check_env_file()
    django_ok = check_django_setup()
    
    # Database check
    print_header("Database Check")
    db_ok = check_database_connection()
    
    # Summary
    print_header("Diagnostic Summary")
    
    all_critical_ok = py_ok and pkg_ok and env_ok and django_ok and db_ok
    
    if all_critical_ok:
        print_success("All critical checks passed!")
        print_info("\nYou can now start the servers:")
        print_info("  Dictionary Server: python run_dictionary_server.py")
        print_info("  Translation Server: python run_translator_server.py")
        
        # Ask if user wants to start servers
        print_header("Start Servers?")
        response = input(f"{Colors.YELLOW}Start dictionary server now? (y/n): {Colors.RESET}").strip().lower()
        
        if response == 'y':
            print_info("\nStarting dictionary server...")
            print_info("Press Ctrl+C to stop")
            time.sleep(2)
            
            # Start server
            try:
                subprocess.run([sys.executable, "run_dictionary_server.py"])
            except KeyboardInterrupt:
                print_info("\nServer stopped by user")
    else:
        print_error("Some critical checks failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()