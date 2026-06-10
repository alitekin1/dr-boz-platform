"""
Telegram Mini App initData verification utility.
Algorithm per Telegram official docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import logging
from typing import Optional
from urllib.parse import unquote

log = logging.getLogger(__name__)


def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Verify Telegram Mini App initData using HMAC-SHA256.
    
    CRITICAL: The data_check_string must use the ORIGINAL URL-encoded values,
    NOT decoded values. parse_qsl() decodes by default, which breaks HMAC verification.
    
    Args:
        init_data: Raw initData string from window.Telegram.WebApp.initData
        bot_token: Telegram bot token
    
    Returns:
        Parsed user dict {id, first_name, last_name?, username?, ...} or None
    """
    try:
        # Manually parse query string WITHOUT URL-decoding values
        # This is critical for HMAC verification to work correctly
        pairs = init_data.split('&')
        parsed = {}
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                parsed[key] = value
        
        received_hash = parsed.pop('hash', None)
        parsed.pop('signature', None)
        if not received_hash:
            log.warning('No hash in initData')
            return None
        
        # Sort alphabetically by key and build check string
        # Values must be kept as-is (URL-encoded), NOT decoded
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(parsed.items())
        )
        
        log.info('RAW initData: %r', init_data)
        log.info('Parsed keys: %s', sorted(parsed.keys()))
        log.info('data_check_string: %r', data_check_string)
        
        # Secret key is SHA256 of bot token
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        
        # Compute HMAC-SHA256
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(computed_hash, received_hash):
            log.warning(
                'initData hash mismatch. keys=%s, received_hash=%s, computed_hash=%s',
                list(parsed.keys()),
                received_hash,
                computed_hash,
            )
            return None
        
        # Parse user JSON - the user field IS URL-encoded, so decode it
        user_json_raw = parsed.get('user', '{}')
        user_json = unquote(user_json_raw)
        user = json.loads(user_json)
        
        if 'id' not in user:
            log.warning('No user id in initData')
            return None
        
        return user
        
    except Exception as e:
        log.error(f'Error verifying initData: {e}')
        return None
