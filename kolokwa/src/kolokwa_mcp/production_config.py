"""
Production Configuration for Kolokwa MCP Servers
With WorkOS Authentication Integration
"""

import os
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple
import re

# Third-party imports
try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError("fastmcp is required. Install with: pip install fastmcp")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import workos
    WORKOS_AVAILABLE = True
except ImportError:
    WORKOS_AVAILABLE = False
    print("Warning: workos library not installed. Install with: pip install workos")


# Custom exception class for MCP operations
class MCPError(Exception):
    """Custom exception for MCP operations"""
    pass


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration for MCP servers - reads from single .env file"""
    
    # Environment detection
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')
    IS_PRODUCTION = ENVIRONMENT == 'production'
    
    # Server settings
    SERVER_NAME = os.getenv('MCP_SERVER_NAME', 'kolokwa-mcp')
    
    # Transport configuration
    TRANSPORT = os.getenv('MCP_TRANSPORT', 'http' if IS_PRODUCTION else 'stdio')
    HTTP_HOST = os.getenv('MCP_HTTP_HOST', '0.0.0.0')
    HTTP_PORT = int(os.getenv('MCP_HTTP_PORT', '8000'))
    
    # CORS settings for web access
    CORS_ENABLED = os.getenv('CORS_ENABLED', 'True').lower() in ('true', '1', 'yes')
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
    
    # SSL/TLS settings for production
    SSL_ENABLED = os.getenv('SSL_ENABLED', str(IS_PRODUCTION)).lower() in ('true', '1', 'yes')
    SSL_CERTFILE = os.getenv('SSL_CERTFILE', '')
    SSL_KEYFILE = os.getenv('SSL_KEYFILE', '')
    
    # Authentication settings
    AUTH_ENABLED = os.getenv('MCP_AUTH_ENABLED', str(IS_PRODUCTION)).lower() in ('true', '1', 'yes')
    
    # WorkOS Configuration
    WORKOS_API_KEY = os.getenv('WORKOS_API_KEY', '')
    WORKOS_CLIENT_ID = os.getenv('WORKOS_CLIENT_ID', '')
    WORKOS_ORGANIZATION_ID = os.getenv('WORKOS_ORGANIZATION_ID', '')
    
    # OAuth settings (WorkOS URLs)
    OAUTH_AUTHORIZE_URL = os.getenv('OAUTH_AUTHORIZE_URL', 'https://api.workos.com/sso/authorize')
    OAUTH_TOKEN_URL = os.getenv('OAUTH_TOKEN_URL', 'https://api.workos.com/sso/token')
    OAUTH_SCOPES = os.getenv('OAUTH_SCOPES', 'openid profile email').split()
    
    # Session/Token Settings
    SESSION_SECRET = os.getenv('SESSION_SECRET', os.getenv('SECRET_KEY', ''))
    JWT_SECRET = os.getenv('JWT_SECRET', os.getenv('SECRET_KEY', ''))
    TOKEN_EXPIRY = int(os.getenv('TOKEN_EXPIRY', '3600'))
    
    # Cache settings
    CACHE_ENABLED = os.getenv('CACHE_ENABLED', str(IS_PRODUCTION)).lower() in ('true', '1', 'yes')
    CACHE_TTL = int(os.getenv('CACHE_TTL', '300'))
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Performance settings
    MAX_SEARCH_RESULTS = int(os.getenv('MAX_SEARCH_RESULTS', '50'))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
    
    # Rate limiting
    RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', str(IS_PRODUCTION)).lower() in ('true', '1', 'yes')
    RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
    RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO' if IS_PRODUCTION else 'DEBUG')
    LOG_FILE = os.getenv('LOG_FILE', '')


# ============================================================================
# WORKOS AUTHENTICATION
# ============================================================================

class WorkOSAuth:
    """WorkOS authentication integration"""
    
    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.enabled = Config.AUTH_ENABLED and WORKOS_AVAILABLE and Config.WORKOS_API_KEY
        self.client = None
        
        if self.enabled:
            try:
                # Initialize WorkOS client
                workos.api_key = Config.WORKOS_API_KEY
                workos.client_id = Config.WORKOS_CLIENT_ID
                self.client = workos
                self.logger.info("WorkOS authentication initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize WorkOS: {e}")
                self.enabled = False
        elif Config.AUTH_ENABLED and not WORKOS_AVAILABLE:
            self.logger.warning("Auth enabled but workos library not installed!")
        elif Config.AUTH_ENABLED and not Config.WORKOS_API_KEY:
            self.logger.warning("Auth enabled but WORKOS_API_KEY not configured!")
    
    def get_authorization_url(self, redirect_uri: str, state: str = None) -> str:
        """Get WorkOS authorization URL"""
        if not self.enabled:
            return ""
        
        try:
            params = {
                'client_id': Config.WORKOS_CLIENT_ID,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope': ' '.join(Config.OAUTH_SCOPES)
            }
            
            if state:
                params['state'] = state
            
            if Config.WORKOS_ORGANIZATION_ID:
                params['organization'] = Config.WORKOS_ORGANIZATION_ID
            
            from urllib.parse import urlencode
            return f"{Config.OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
        except Exception as e:
            self.logger.error(f"Error generating auth URL: {e}")
            return ""
    
    def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        if not self.enabled:
            return None
        
        try:
            # Use WorkOS to get profile
            profile = self.client.sso.get_profile_and_token(code)
            
            return {
                'access_token': profile.access_token,
                'profile': {
                    'id': profile.id,
                    'email': profile.email,
                    'first_name': profile.first_name,
                    'last_name': profile.last_name,
                    'organization_id': profile.organization_id
                }
            }
        except Exception as e:
            self.logger.error(f"Error exchanging code for token: {e}")
            return None
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode access token"""
        if not self.enabled:
            return None
        
        try:
            # Verify with WorkOS
            profile = self.client.user_management.get_user(token)
            return {
                'valid': True,
                'user': {
                    'id': profile.id,
                    'email': profile.email
                }
            }
        except Exception as e:
            self.logger.error(f"Token verification failed: {e}")
            return None


# ============================================================================
# SECURITY: SENSITIVE DATA MASKING
# ============================================================================

def mask_sensitive_data(text: str) -> str:
    """Mask sensitive information in logs"""
    if not isinstance(text, str):
        text = str(text)
    
    # Mask Redis URLs
    text = re.sub(
        r'redis://([^:]+):([^@]+)@',
        r'redis://\1:***MASKED***@',
        text
    )
    
    # Mask database passwords
    text = re.sub(
        r'(password|PASSWORD|pwd|PWD)(["\']?\s*[:=]\s*["\']?)([^"\'\s&]+)',
        r'\1\2***MASKED***',
        text
    )
    
    # Mask API keys (including WorkOS)
    text = re.sub(
        r'(sk_[a-zA-Z0-9_-]{20,})',
        r'sk_***MASKED***',
        text
    )
    
    # Mask tokens
    text = re.sub(
        r'(token|TOKEN|secret|SECRET)(["\']?\s*[:=]\s*["\']?)([^"\'\s&]{10,})',
        r'\1\2***MASKED***',
        text
    )
    
    # Mask WorkOS client secrets
    text = re.sub(
        r'(client_[a-zA-Z0-9_-]{20,})',
        r'client_***MASKED***',
        text
    )
    
    return text


# ============================================================================
# LOGGING SETUP
# ============================================================================

class SecureFormatter(logging.Formatter):
    """Custom formatter that masks sensitive data"""
    
    def format(self, record):
        formatted = super().format(record)
        return mask_sensitive_data(formatted)


def setup_logging():
    """Configure logging with security"""
    logger = logging.getLogger('kolokwa_mcp')
    logger.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    formatter = SecureFormatter(
        '%(levelname)s %(asctime)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # Clear existing handlers and add console
    logger.handlers.clear()
    logger.addHandler(console_handler)
    
    # Add file handler if configured
    if Config.LOG_FILE:
        try:
            os.makedirs(os.path.dirname(Config.LOG_FILE), exist_ok=True)
            file_handler = logging.FileHandler(Config.LOG_FILE)
            file_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create file handler: {e}")
    
    return logger


logger = setup_logging()


# Initialize WorkOS auth (after logger is created)
workos_auth = WorkOSAuth(logger)


# ============================================================================
# REDIS CACHE
# ============================================================================

class CacheManager:
    """Manage Redis caching"""
    
    def __init__(self):
        self.enabled = Config.CACHE_ENABLED and REDIS_AVAILABLE
        self.client = None
        
        if self.enabled:
            try:
                self.client = redis.from_url(
                    Config.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                self.client.ping()
                logger.info("Redis cache connected successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed: {type(e).__name__}. Caching disabled.")
                self.enabled = False
                self.client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.enabled:
            return None
        try:
            return self.client.get(key)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value in cache"""
        if not self.enabled:
            return False
        try:
            ttl = ttl or Config.CACHE_TTL
            self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.enabled:
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False


cache = CacheManager()


# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

class MetricsCollector:
    """Track server performance metrics"""
    
    def __init__(self):
        self.metrics = {}
        self.endpoint_metrics = {}
        self.start_time = time.time()
    
    def record_request(self, endpoint: str, duration: float, success: bool):
        """Record a request"""
        if endpoint not in self.endpoint_metrics:
            self.endpoint_metrics[endpoint] = {
                'count': 0,
                'total_time': 0,
                'errors': 0
            }
        
        self.endpoint_metrics[endpoint]['count'] += 1
        self.endpoint_metrics[endpoint]['total_time'] += duration
        if not success:
            self.endpoint_metrics[endpoint]['errors'] += 1
    
    def get_stats(self) -> dict:
        """Get current statistics"""
        total = sum(m['count'] for m in self.endpoint_metrics.values())
        successful_requests = total - sum(m['errors'] for m in self.endpoint_metrics.values())
        total_time = sum(m['total_time'] for m in self.endpoint_metrics.values())
        uptime = time.time() - self.start_time
        
        stats = {
            **self.metrics,
            'uptime_seconds': uptime,
            'successful_requests': successful_requests,
            'total_response_time': total_time,
            'success_rate': successful_requests / total if total > 0 else 0,
            'avg_response_time': total_time / total if total > 0 else 0,
            'endpoints': {}
        }
        
        for endpoint, data in self.endpoint_metrics.items():
            if data['count'] > 0:
                stats['endpoints'][endpoint] = {
                    'requests': data['count'],
                    'avg_time': data['total_time'] / data['count'],
                    'errors': data['errors'],
                    'error_rate': data['errors'] / data['count']
                }
        
        return stats


metrics = MetricsCollector()


# ============================================================================
# SERVER CREATION WITH WORKOS
# ============================================================================

def create_server(name: str) -> FastMCP:
    """
    Create a FastMCP server with WorkOS authentication
    
    Args:
        name: Server name
    
    Returns:
        Configured FastMCP instance
    """
    server_config = {
        'name': name,
    }
    
    # Add WorkOS OAuth configuration if enabled
    if Config.AUTH_ENABLED and workos_auth.enabled:
        logger.info("Configuring WorkOS OAuth authentication")
        server_config['auth'] = {
            'client_id': Config.WORKOS_CLIENT_ID,
            'client_secret': Config.WORKOS_API_KEY,
            'authorize_url': Config.OAUTH_AUTHORIZE_URL,
            'token_url': Config.OAUTH_TOKEN_URL,
            'scopes': Config.OAUTH_SCOPES
        }
    else:
        if Config.AUTH_ENABLED:
            logger.warning("Auth enabled but WorkOS not properly configured!")
    
    mcp = FastMCP(**server_config)
    
    env = "production" if Config.IS_PRODUCTION else "development"
    transport = Config.TRANSPORT
    logger.info(f"FastMCP server '{name}' initialized for {env} environment")
    logger.info(f"Transport: {transport}, Debug: {Config.DEBUG}, Auth: {Config.AUTH_ENABLED}, Cache: {Config.CACHE_ENABLED}")
    
    return mcp


# ============================================================================
# DECORATORS
# ============================================================================

def handle_errors(func: Callable) -> Callable:
    """Async error handling decorator"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {type(e).__name__}: {str(e)}")
            raise MCPError(f"Operation failed: {str(e)}")
    return wrapper


def handle_errors_sync(func: Callable) -> Callable:
    """Sync error handling decorator"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {type(e).__name__}: {str(e)}")
            raise MCPError(f"Operation failed: {str(e)}")
    return wrapper


def track_performance(endpoint: str):
    """Track performance metrics for endpoints"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = time.time() - start_time
                metrics.record_request(endpoint, duration, success)
        return wrapper
    return decorator


def get_cached_or_compute(cache_key: str, compute_func: Callable, ttl: int = None) -> Any:
    """Get from cache or compute and cache the result"""
    if not cache.enabled:
        return compute_func()
    
    cached = cache.get(cache_key)
    if cached is not None:
        try:
            import json
            return json.loads(cached)
        except:
            pass
    
    result = compute_func()
    try:
        import json
        cache.set(cache_key, json.dumps(result), ttl)
    except:
        pass
    
    return result


# ============================================================================
# HEALTH CHECKS
# ============================================================================

def check_database_health() -> Tuple[bool, str]:
    """Check if database is accessible"""
    try:
        from dictionary.models import KoloquaEntry
        KoloquaEntry.objects.count()
        return True, "Database is healthy"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def check_redis_health() -> Tuple[bool, str]:
    """Check if Redis is accessible"""
    if not cache.enabled:
        return True, "Redis not enabled"
    
    try:
        cache.client.ping()
        return True, "Redis is healthy"
    except Exception as e:
        return False, f"Redis error: {str(e)}"


def check_workos_health() -> Tuple[bool, str]:
    """Check if WorkOS is configured"""
    if not Config.AUTH_ENABLED:
        return True, "Auth not enabled"
    
    if not workos_auth.enabled:
        return False, "WorkOS not properly configured"
    
    return True, "WorkOS configured"


# ============================================================================
# STARTUP INFO
# ============================================================================

def print_startup_info():
    """Print masked startup information"""
    logger.info("=" * 60)
    logger.info("Kolokwa MCP Server Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {Config.ENVIRONMENT}")
    logger.info(f"Transport: {Config.TRANSPORT}")
    
    if Config.TRANSPORT == 'http':
        protocol = 'https' if Config.SSL_ENABLED else 'http'
        logger.info(f"Server URL: {protocol}://{Config.HTTP_HOST}:{Config.HTTP_PORT}")
        logger.info(f"API Docs: {protocol}://{Config.HTTP_HOST}:{Config.HTTP_PORT}/docs")
    
    logger.info(f"Debug Mode: {Config.DEBUG}")
    logger.info(f"Authentication: {'ENABLED (WorkOS)' if Config.AUTH_ENABLED else 'DISABLED'}")
    logger.info(f"Caching: {'ENABLED' if Config.CACHE_ENABLED else 'DISABLED'}")
    logger.info(f"CORS: {'ENABLED' if Config.CORS_ENABLED else 'DISABLED'}")
    
    # Database info
    from django.conf import settings
    db_engine = settings.DATABASES['default']['ENGINE']
    if 'sqlite' in db_engine:
        logger.info("Database: SQLite")
    elif 'postgresql' in db_engine:
        db_host = settings.DATABASES['default'].get('HOST', 'localhost')
        logger.info(f"Database: PostgreSQL ({db_host})")
    
    # Redis info
    if Config.CACHE_ENABLED and REDIS_AVAILABLE:
        masked_redis = mask_sensitive_data(Config.REDIS_URL)
        logger.info(f"Redis: {masked_redis}")
    
    logger.info("=" * 60)


# ============================================================================
# HTTP SERVER RUNNER
# ============================================================================

def run_http_server(mcp_instance: FastMCP, port: int = None, host: str = None):
    """Run MCP server with HTTP transport"""
    import uvicorn
    
    port = port or Config.HTTP_PORT
    host = host or Config.HTTP_HOST
    
    uvicorn_config = {
        'host': host,
        'port': port,
        'log_level': Config.LOG_LEVEL.lower(),
        'access_log': not Config.IS_PRODUCTION,
        'timeout_keep_alive': Config.REQUEST_TIMEOUT,
    }
    
    # Add SSL configuration for production
    if Config.SSL_ENABLED and Config.SSL_CERTFILE and Config.SSL_KEYFILE:
        uvicorn_config['ssl_certfile'] = Config.SSL_CERTFILE
        uvicorn_config['ssl_keyfile'] = Config.SSL_KEYFILE
        logger.info("SSL/TLS enabled")
    
    logger.info(f"Starting HTTP server on {host}:{port}")
    
    uvicorn.run(mcp_instance, **uvicorn_config)