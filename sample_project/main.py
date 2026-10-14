from users import get_user
from database import connect_database


def main():
    connect_database()

    user = get_user(1)

    if user:
        print(f"Welcome, {user['name']}!")
    else:
        print("User not found.")


if __name__ == "__main__":
    main()