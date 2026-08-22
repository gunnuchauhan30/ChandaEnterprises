"""
Single shared slowapi Limiter instance. Lives in its own module (not in
main.py) so route modules like app/api/v1/auth.py can import it with
`@limiter.limit(...)` without causing a circular import
(main.py -> router.py -> auth.py -> main.py).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
