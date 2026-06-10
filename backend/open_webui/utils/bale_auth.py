"""
Bale Mini App initData verification utility.
Bale is based on Telegram's open-source code.
Uses same HMAC-SHA256 verification pattern with separate bot token.
"""

import hashlib
import hmac
import json
import logging
from typing import Optional
from urllib.parse import unquote

log = logging.getLogger(__name__)


def verify_bale_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Verify Bale Mini App initData.
    
    Bale uses the same algorithm as Telegram (HMAC-SHA256)
    but with its own bot token.
    
    CRITICAL: The data_check_string must use the ORIGINAL URL-encoded values,
    NOT decoded values. parse_qsl() decodes by default, which breaks HMAC verification.
    
    Args:
        init_data: Raw initData string from window.Bale.WebApp.initData
        bot_token: Bale bot token
    
    Returns:
        Parsed user dict {id, first_name, ...} or None
    """
    try:
        # Manually parse query string WITHOUT URL-decoding values
        pairs = init_data.split('&')
        parsed = {}
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                parsed[key] = value
        
        received_hash = parsed.pop('hash', None)
        parsed.pop('signature', None)
        if not received_hash:
            log.warning('No hash in Bale initData')
            return None
        
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(parsed.items())
        )
        
        log.debug('Bale data_check_string: %s', repr(data_check_string))
        
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(computed_hash, received_hash):
            log.warning(
                'Bale initData hash mismatch. keys=%s',
                list(parsed.keys()),
            )
            return None
        
        # Parse user JSON - the user field IS URL-encoded, so decode it
        user_json = unquote(parsed.get('user', '{}'))
        user = json.loads(user_json)
        
        if 'id' not in user:
            log.warning('No user id in Bale initData')
            return None
        
        return user
        
    except Exception as e:
        log.error(f'Error verifying Bale initData: {e}')
        return None
