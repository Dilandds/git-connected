_current_user: dict = None


def set_user(profile: dict) -> None:
    global _current_user
    _current_user = profile


def get_user() -> dict:
    return _current_user


def clear_user() -> None:
    global _current_user
    _current_user = None


def is_logged_in() -> bool:
    return _current_user is not None


def get_role() -> str:
    return _current_user.get('role') if _current_user else None


def get_full_name() -> str:
    return _current_user.get('full_name') if _current_user else None


def get_company_id() -> str:
    return _current_user.get('company_id') if _current_user else None
