def get_user(user_id):
    users = {
        1: {"name": "Rahul", "role": "Developer"},
        2: {"name": "Priya", "role": "Designer"},
    }

    return users.get(user_id)