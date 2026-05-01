# Orange Users API — Setup and Integration Guide

## Base URL
`http://localhost:8000/api/auth/`

---

## 1) PostgreSQL Database Setup

### Install PostgreSQL
Download and install PostgreSQL for your operating system using the default options.

### Create the database and user
Open `psql` or pgAdmin and run:

    CREATE DATABASE users_orange;

    CREATE USER postgres WITH PASSWORD '0000';

    GRANT ALL PRIVILEGES ON DATABASE users_orange TO postgres;

You may change the database user and password, but then the `.env` file must be updated to match.

---

## 2) Configure the `.env` File

Create a `.env` file in the backend project root, at the same level as `manage.py`:

    DB_NAME=users_orange
    DB_USER=postgres
    DB_PASSWORD=0000
    DB_HOST=localhost
    DB_PORT=5432
    DJ_SECRET_KEY=django-insecure-your-secret-key

### Notes
- `DJ_SECRET_KEY` should be a long random secret key.
- You can generate one with Python:

    from django.core.management.utils import get_random_secret_key
    print(get_random_secret_key())

- Keep the `.env` file private and do not commit it to version control.

---

## 3) Run Django Migrations

Activate your virtual environment:

    cd /path/to/project
    venv\Scripts\activate   # Windows
    # source venv/bin/activate   # macOS / Linux

Install dependencies if needed:

    pip install -r requirements.txt

Apply migrations:

    python manage.py makemigrations
    python manage.py migrate

---

## 4) Create Test Data

You can insert test roles and users using Django shell:

    python manage.py shell

Then run:

    import bcrypt
    from api.models import User, Role

    admin_role = Role.objects.create(
        role='admin',
        permissions=['read', 'write', 'delete', 'manage']
    )

    user_role = Role.objects.create(
        role='user',
        permissions=['read']
    )

    User.objects.create(
        fullname='Ahmed Abidi',
        email='ahmed.abidi@orange.com',
        password=bcrypt.hashpw('password123'.encode(), bcrypt.gensalt()).decode(),
        role=admin_role
    )

    User.objects.create(
        fullname='John Doe',
        email='john@example.com',
        password=bcrypt.hashpw('123456'.encode(), bcrypt.gensalt()).decode(),
        role=user_role
    )

These users can now be used to test the API.

---

## 5) Authentication and Authorization

All protected endpoints require the following header:

    Authorization: Bearer <token>

The token is returned by the login endpoint.

---

## 6) API Endpoints

### 6.1 Login
**Method:** `POST`  
**URL:** `http://localhost:8000/api/auth/login/`

#### Request Body
    {
      "email": "ahmed.abidi@orange.com",
      "password": "password123"
    }

#### Success Response
    {
      "token": "your.jwt.token",
      "user": {
        "id": 3,
        "fullname": "Ahmed Abidi",
        "email": "ahmed.abidi@orange.com",
        "role": "admin",
        "permissions": ["read", "write", "delete", "manage"]
      }
    }

#### Notes
- Use the returned token for every protected request.
- Keep the token in the `Authorization` header as `Bearer <token>`.

---

### 6.2 Logout
**Method:** `POST`  
**URL:** `http://localhost:8000/api/auth/logout/`

#### Headers
    Authorization: Bearer <token>

#### Success Response
    {
      "message": "Logout successful"
    }

---

### 6.3 Get All Users
**Method:** `GET`  
**URL:** `http://localhost:8000/api/auth/myusers/`

#### Access
Admin only.

#### Headers
    Authorization: Bearer <token>

#### Success Response
    [
      {
        "id": 1,
        "fullname": "John Doe",
        "email": "john@example.com",
        "role": "manager"
      },
      {
        "id": 2,
        "fullname": "Jane Smith",
        "email": "jane@example.com",
        "role": "user"
      }
    ]

---

### 6.4 Get Single User
**Method:** `GET`  
**URL:** `http://localhost:8000/api/auth/myusers/<user_id>/`

#### Example
`http://localhost:8000/api/auth/myusers/1/`

#### Headers
    Authorization: Bearer <token>

#### Success Response
    {
      "id": 1,
      "fullname": "John Doe",
      "email": "john@example.com",
      "role": "manager",
      "permissions": ["read"]
    }

---

### 6.5 Delete User
**Method:** `DELETE`  
**URL:** `http://localhost:8000/api/auth/users/<user_id>/delete/`

#### Example
`http://localhost:8000/api/auth/users/2/delete/`

#### Access
Admin only.

#### Headers
    Authorization: Bearer <token>

#### Success Response
    {
      "message": "User deleted"
    }

#### Notes
- Non-admin users receive `403 Forbidden`.

---

### 6.6 Get Logs
**Method:** `GET`  
**URL:** `http://localhost:8000/api/auth/logs/`

#### Access
Admin only.

#### Headers
    Authorization: Bearer <token>

#### Success Response
    [
      {
        "id": 1,
        "user": "ahmed.abidi@orange.com",
        "action": "login",
        "ip": "127.0.0.1",
        "detail": "User logged in",
        "created_at": "2026-03-24T22:10:00Z"
      },
      {
        "id": 2,
        "user": "ahmed.abidi@orange.com",
        "action": "logout",
        "ip": "127.0.0.1",
        "detail": "User logged out",
        "created_at": "2026-03-24T22:15:00Z"
      }
    ]

---

## 7) Frontend Integration Notes

### Login flow
1. Send credentials to `/login/`.
2. Save the returned token.
3. Attach the token to every protected request.

### Protected requests
Use this header format:

    Authorization: Bearer <token>

### Role-based access
- Admin can call:
  - `GET /myusers/`
  - `DELETE /users/<id>/delete/`
  - `GET /logs/`
- Regular users can call:
  - `GET /myusers/<id>/`
  - `POST /logout/`

### Common error responses
- `401 Unauthorized` → invalid or expired token
- `403 Forbidden` → user does not have permission
- `404 Not Found` → user or resource does not exist

---

## 8) Quick Testing Example

### Login
    curl -X POST http://localhost:8000/api/auth/login/ ^
    -H "Content-Type: application/json" ^
    -d "{\"email\":\"ahmed.abidi@orange.com\",\"password\":\"password123\"}"

### Get all users
    curl -H "Authorization: Bearer <token>" http://localhost:8000/api/auth/myusers/

### Get one user
    curl -H "Authorization: Bearer <token>" http://localhost:8000/api/auth/myusers/1/

### Delete a user
    curl -X DELETE -H "Authorization: Bearer <token>" http://localhost:8000/api/auth/users/2/delete/

### Get logs
    curl -H "Authorization: Bearer <token>" http://localhost:8000/api/auth/logs/

---

## 9) Summary

- Database: PostgreSQL
- Base API path: `http://localhost:8000/api/auth/`
- Authentication: JWT token
- Admin-only endpoints: users list, delete user, logs
- Test users: create them in Django shell with hashed passwords