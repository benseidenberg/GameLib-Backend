class User:
    def __init__(self, id: int, email: str, password: str):
        self.id = id
        self.email = email
        self.password = password

    def __repr__(self):
        return f"User(id={self.id}, email='{self.email}')"

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "password": self.password
        }