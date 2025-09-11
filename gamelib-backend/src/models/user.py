class User:
    def __init__(self, steam_id: int):
        self.steam_id = steam_id
        self.data = None  # Placeholder for additional user data

    def __repr__(self):
        return f"User(id={self.steam_id}')"

    def to_dict(self):
        return {
            "steam_id": self.steam_id,
            "data": self.data
        }