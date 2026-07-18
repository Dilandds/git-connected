from supabase import create_client, Client

try:
    from config import SUPABASE_URL, SUPABASE_KEY
except ImportError:
    # Production — keys are hardcoded here for distribution
    SUPABASE_URL = "https://jgdzssucagwkgucejqqx.supabase.co"
    SUPABASE_KEY = "sb_publishable_297QJn5R7ltaUAiAcO7riw_pr0SI26O"

_client: Client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client
