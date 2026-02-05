-- MySQL Test Database Initialization
-- This script runs automatically when the container starts
-- MySQL automatically uses the database specified in MYSQL_DATABASE env var

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INT DEFAULT 0,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending',
    total_amount DECIMAL(10, 2),
    shipping_address TEXT,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(10, 2) NOT NULL,
    INDEX idx_order_id (order_id),
    INDEX idx_product_id (product_id),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INT NULL,
    FOREIGN KEY (parent_id) REFERENCES categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert sample users
INSERT INTO users (username, email, first_name, last_name) VALUES
('john_doe', 'john.doe@example.com', 'John', 'Doe'),
('jane_smith', 'jane.smith@example.com', 'Jane', 'Smith'),
('bob_wilson', 'bob.wilson@example.com', 'Bob', 'Wilson'),
('alice_johnson', 'alice.johnson@example.com', 'Alice', 'Johnson'),
('charlie_brown', 'charlie.brown@example.com', 'Charlie', 'Brown')
ON DUPLICATE KEY UPDATE username=username;

-- Insert sample categories
INSERT INTO categories (name, description) VALUES
('Electronics', 'Electronic devices and accessories'),
('Clothing', 'Apparel and fashion items'),
('Books', 'Physical and digital books'),
('Home & Garden', 'Home improvement and garden supplies'),
('Sports', 'Sports equipment and accessories')
ON DUPLICATE KEY UPDATE name=name;

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

-- Display summary
SELECT 'MySQL test database initialized successfully!' AS message;
SELECT CONCAT('Users: ', COUNT(*)) AS info FROM users
UNION ALL
SELECT CONCAT('Products: ', COUNT(*)) FROM products
UNION ALL
SELECT CONCAT('Orders: ', COUNT(*)) FROM orders
UNION ALL
SELECT CONCAT('Categories: ', COUNT(*)) FROM categories;
