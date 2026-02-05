-- PostgreSQL Test Database Initialization
-- This script runs automatically when the container starts

-- Create test schema
CREATE SCHEMA IF NOT EXISTS test_schema;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending',
    total_amount DECIMAL(10, 2),
    shipping_address TEXT
);

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(10, 2) NOT NULL
);

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INTEGER REFERENCES categories(id)
);

-- Insert sample users
INSERT INTO users (username, email, first_name, last_name) VALUES
('john_doe', 'john.doe@example.com', 'John', 'Doe'),
('jane_smith', 'jane.smith@example.com', 'Jane', 'Smith'),
('bob_wilson', 'bob.wilson@example.com', 'Bob', 'Wilson'),
('alice_johnson', 'alice.johnson@example.com', 'Alice', 'Johnson'),
('charlie_brown', 'charlie.brown@example.com', 'Charlie', 'Brown')
ON CONFLICT (username) DO NOTHING;

-- Insert sample categories
INSERT INTO categories (name, description) VALUES
('Electronics', 'Electronic devices and accessories'),
('Clothing', 'Apparel and fashion items'),
('Books', 'Physical and digital books'),
('Home & Garden', 'Home improvement and garden supplies'),
('Sports', 'Sports equipment and accessories')
ON CONFLICT (name) DO NOTHING;

-- Insert sample products
INSERT INTO products (name, description, price, stock_quantity, category) VALUES
('Laptop Pro 15', 'High-performance laptop with 16GB RAM', 1299.99, 50, 'Electronics'),
('Wireless Mouse', 'Ergonomic wireless mouse with USB receiver', 29.99, 200, 'Electronics'),
('Cotton T-Shirt', 'Comfortable 100% cotton t-shirt', 19.99, 150, 'Clothing'),
('Running Shoes', 'Professional running shoes with gel cushioning', 89.99, 75, 'Sports'),
('Programming Book', 'Complete guide to modern software development', 49.99, 100, 'Books'),
('Coffee Maker', 'Automatic coffee maker with timer', 79.99, 60, 'Home & Garden'),
('Desk Lamp', 'LED desk lamp with adjustable brightness', 34.99, 120, 'Home & Garden'),
('Headphones', 'Noise-canceling over-ear headphones', 199.99, 80, 'Electronics'),
('Yoga Mat', 'Non-slip exercise yoga mat', 24.99, 90, 'Sports'),
('Cookbook', 'Healthy recipes for everyday cooking', 29.99, 110, 'Books');

-- Insert sample orders
INSERT INTO orders (user_id, status, total_amount, shipping_address) VALUES
(1, 'completed', 1329.98, '123 Main St, New York, NY 10001'),
(2, 'pending', 109.98, '456 Oak Ave, Los Angeles, CA 90001'),
(3, 'shipped', 199.99, '789 Pine Rd, Chicago, IL 60601'),
(1, 'completed', 54.98, '123 Main St, New York, NY 10001'),
(4, 'pending', 89.99, '321 Elm St, Houston, TX 77001');

-- Insert sample order items
INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES
(1, 1, 1, 1299.99, 1299.99),
(1, 2, 1, 29.99, 29.99),
(2, 4, 1, 89.99, 89.99),
(2, 3, 1, 19.99, 19.99),
(3, 8, 1, 199.99, 199.99),
(4, 5, 1, 49.99, 49.99),
(4, 10, 1, 29.99, 29.99),
(5, 4, 1, 89.99, 89.99);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);

-- Create a view for order summaries
CREATE OR REPLACE VIEW order_summary AS
SELECT 
    o.id AS order_id,
    u.username,
    u.email,
    o.order_date,
    o.status,
    o.total_amount,
    COUNT(oi.id) AS item_count
FROM orders o
JOIN users u ON o.user_id = u.id
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, u.username, u.email, o.order_date, o.status, o.total_amount;

-- Grant permissions (if needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- Display summary
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL test database initialized successfully!';
    RAISE NOTICE 'Users: %', (SELECT COUNT(*) FROM users);
    RAISE NOTICE 'Products: %', (SELECT COUNT(*) FROM products);
    RAISE NOTICE 'Orders: %', (SELECT COUNT(*) FROM orders);
    RAISE NOTICE 'Categories: %', (SELECT COUNT(*) FROM categories);
END $$;
