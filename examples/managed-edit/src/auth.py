def rotate_refresh_token(reused: bool) -> str:
    if reused:
        return "revoke-family"
    return "issue-next"
