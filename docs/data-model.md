# API-Sentinel Database Model

## Overview

API-Sentinel uses SQLite for its mock e-commerce services. The database
contains customer, order, and invoice records used for authentication,
API testing, and authorization testing.

The Docker services share a database volume. The pytest suite uses a
separate test database so automated tests do not modify application data.

## Tables

### `customers`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `username` | Unique login name |
| `full_name` | Customer display name |
| `email` | Customer email |
| `password_hash` | Hashed password |
| `created_at` | Record creation timestamp |

### `orders`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `user_id` | Customer ID associated with the order |
| `item` | Ordered product |
| `total` | Order total |
| `status` | Order status |
| `created_at` | Record creation timestamp |

`user_id` references `customers.id`.

### `invoices`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `order_id` | Unique associated order ID |
| `owner_id` | Customer who owns the invoice |
| `amount` | Invoice amount |
| `currency` | Currency code |
| `status` | Invoice payment status |
| `card_last4` | Last four digits used in mock payment data |
| `billing_address` | Mock billing address |
| `created_at` | Record creation timestamp |

`order_id` references `orders.id`, and `owner_id` references `customers.id`.

## Indexes

The schema defines indexes on:

- `orders.user_id`
- `invoices.owner_id`
- `invoices.order_id`

These support common order and invoice lookups.

## Security testing notes

- Passwords are stored as hashes, not plaintext.
- SQL queries should use parameterized statements.
- Authentication must not be treated as authorization.
- An authenticated user should only access objects they are authorized to access.
- BOLA testing checks whether changing an object identifier exposes another
  user's data.
- Any intentionally vulnerable BOLA behavior is for the local test lab only.

## Database safety

The production seed script rebuilds the customers, orders, and invoices
tables. Run it only against a disposable or explicitly approved database.
The pytest database must remain separate from the shared application database.
