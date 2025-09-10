# GameLib Backend

This project is a backend application built using FastAPI and Supabase to manage a user database and handle requests for the GameLib website.

## Project Structure

```
gamelib-backend
├── src
│   ├── main.py               # Entry point of the FastAPI application
│   ├── api                   # Contains API route definitions
│   │   ├── __init__.py       # Marks the api directory as a package
│   │   └── users.py          # User-related API endpoints
│   ├── db                    # Database interaction layer
│   │   ├── __init__.py       # Marks the db directory as a package
│   │   └── supabase_client.py # Supabase client initialization
│   ├── models                # Data models
│   │   ├── __init__.py       # Marks the models directory as a package
│   │   └── user.py           # User model definition
│   └── schemas               # Data validation schemas
│       ├── __init__.py       # Marks the schemas directory as a package
│       └── user_schema.py     # User data validation schemas
├── requirements.txt           # Project dependencies
├── README.md                  # Project documentation
└── .env                       # Environment variables
```

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   cd gamelib-backend
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the root directory and add your Supabase URL and API keys:
   ```
   SUPABASE_URL=<your-supabase-url>
   SUPABASE_KEY=<your-supabase-key>
   ```

5. Run the FastAPI application:
   ```
   uvicorn src.main:app --reload
   ```

## API Endpoints

- **User Creation**: `POST /users`
- **User Retrieval**: `GET /users/{id}`
- **User Update**: `PUT /users/{id}`
- **User Deletion**: `DELETE /users/{id}`

## Usage

You can interact with the API using tools like Postman or cURL. Make sure to replace `{id}` with the actual user ID when making requests.

## License

This project is licensed under the MIT License.