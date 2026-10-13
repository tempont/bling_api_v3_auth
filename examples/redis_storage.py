"""Share tokens between several processes/hosts using Redis.

    pip install "bling-api-v3-auth[redis]"

Refreshes are protected by a Redis lock, so concurrent workers never use the same
refresh token twice (Bling rotates it on every refresh).
"""

import redis

from bling_api_v3_auth import BlingAuthManager, BlingConfig, RedisTokenStorage

storage = RedisTokenStorage(
    redis.Redis.from_url("redis://localhost:6379/0"),
    key="bling:minha-empresa:token",  # one key per Bling account
)
manager = BlingAuthManager(BlingConfig.from_env(), storage)

print(manager.get_access_token())
