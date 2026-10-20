def get_user_name(user):
    # BUG: crashes with TypeError when user is None
    return user["name"]
