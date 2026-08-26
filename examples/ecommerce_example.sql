-- QueryWeaver demo schema: 12-table e-commerce
DROP DATABASE IF EXISTS queryweaver_demo;
CREATE DATABASE queryweaver_demo;
\c queryweaver_demo

-- 1. users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(120) UNIQUE NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    signup_date DATE NOT NULL DEFAULT CURRENT_DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2. addresses
CREATE TABLE addresses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    street VARCHAR(160) NOT NULL,
    city VARCHAR(80) NOT NULL,
    state VARCHAR(40),
    postal_code VARCHAR(20),
    country VARCHAR(60) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);

-- 3. categories (self-referencing)
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL
);

-- 4. products
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(40) UNIQUE NOT NULL,
    name VARCHAR(160) NOT NULL,
    description TEXT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    base_price NUMERIC(10,2) NOT NULL CHECK (base_price >= 0)
);

-- 5. product_variants
CREATE TABLE product_variants (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_name VARCHAR(80) NOT NULL,
    sku VARCHAR(40) UNIQUE NOT NULL,
    price NUMERIC(10,2) NOT NULL CHECK (price >= 0)
);

-- 6. suppliers
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    contact_email VARCHAR(120),
    country VARCHAR(60)
);

-- 7. product_suppliers (M:N)
CREATE TABLE product_suppliers (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    lead_time_days INTEGER NOT NULL DEFAULT 7,
    cost NUMERIC(10,2),
    PRIMARY KEY (product_id, supplier_id)
);

-- 8. inventory
CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    warehouse VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 9. orders
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    address_id INTEGER REFERENCES addresses(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total NUMERIC(12,2) NOT NULL DEFAULT 0,
    ordered_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 10. order_items
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    variant_id INTEGER NOT NULL REFERENCES product_variants(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10,2) NOT NULL
);

-- 11. payments
CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    method VARCHAR(30) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    paid_at TIMESTAMP
);

-- 12. reviews
CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, product_id)
);

-- ============================================================
-- Fake data
-- ============================================================

INSERT INTO users (email, full_name, signup_date, is_active) VALUES
    ('alice@example.com',  'Alice Cooper',   '2024-01-15', TRUE),
    ('bob@example.com',    'Bob Dylan',      '2024-02-03', TRUE),
    ('carol@example.com',  'Carol King',     '2024-02-19', TRUE),
    ('dave@example.com',   'Dave Grohl',     '2024-03-08', FALSE),
    ('eve@example.com',    'Eve Polastri',   '2024-04-21', TRUE),
    ('frank@example.com',  'Frank Ocean',    '2024-05-30', TRUE),
    ('grace@example.com',  'Grace Hopper',   '2024-06-12', TRUE),
    ('hank@example.com',   'Hank Williams',  '2024-07-04', FALSE);

INSERT INTO addresses (user_id, street, city, state, postal_code, country, is_default) VALUES
    (1, '123 Main St',     'New York',     'NY', '10001', 'USA',    TRUE),
    (2, '456 Oak Ave',     'Los Angeles',  'CA', '90001', 'USA',    TRUE),
    (3, '789 Pine Rd',     'New York',     'NY', '10002', 'USA',    TRUE),
    (4, '12 Maple Dr',     'Chicago',      'IL', '60601', 'USA',    TRUE),
    (5, '34 Birch Ln',     'London',       NULL, 'EC1A',  'UK',     TRUE),
    (6, '56 Cedar St',     'Toronto',      'ON', 'M5H',   'Canada', TRUE),
    (7, '78 Elm Way',      'Austin',       'TX', '73301', 'USA',    TRUE),
    (8, '90 Spruce Ct',    'Berlin',       NULL, '10115', 'Germany',TRUE),
    (1, '200 Wall St',     'New York',     'NY', '10005', 'USA',    FALSE);

INSERT INTO categories (name, parent_id) VALUES
    ('Electronics',     NULL),  -- 1
    ('Computers',       1),     -- 2
    ('Audio',           1),     -- 3
    ('Home',            NULL),  -- 4
    ('Kitchen',         4),     -- 5
    ('Furniture',       4),     -- 6
    ('Books',           NULL);  -- 7

INSERT INTO products (sku, name, description, category_id, base_price) VALUES
    ('LAP-001', 'UltraBook 14',         'Lightweight 14-inch laptop',          2, 1199.00),
    ('LAP-002', 'GamerPro 17',          '17-inch gaming laptop',                2, 1899.00),
    ('HDP-010', 'StudioPhones X',       'Over-ear studio headphones',           3,  299.00),
    ('SPK-020', 'BoomBox Mini',         'Portable bluetooth speaker',           3,   89.00),
    ('CHR-001', 'ErgoChair Pro',        'Ergonomic office chair',               6,  549.00),
    ('TBL-001', 'Walnut Desk',          'Solid walnut writing desk',            6,  799.00),
    ('PAN-001', 'CastIron Pan 12in',    '12-inch cast iron skillet',            5,   59.00),
    ('KNF-001', 'Chef Knife 8in',       'High-carbon chef knife',               5,  129.00),
    ('BK-001',  'Database Internals',   'Book on database systems',             7,   45.00),
    ('BK-002',  'Designing Data-Intensive Apps', 'The DDIA classic',            7,   55.00);

INSERT INTO product_variants (product_id, variant_name, sku, price) VALUES
    (1,  '16GB / 512GB',  'LAP-001-A', 1199.00),
    (1,  '32GB / 1TB',    'LAP-001-B', 1499.00),
    (2,  'RTX 4070',      'LAP-002-A', 1899.00),
    (2,  'RTX 4080',      'LAP-002-B', 2299.00),
    (3,  'Black',         'HDP-010-K',  299.00),
    (3,  'White',         'HDP-010-W',  299.00),
    (4,  'Black',         'SPK-020-K',   89.00),
    (4,  'Red',           'SPK-020-R',   89.00),
    (5,  'Standard',      'CHR-001-S',  549.00),
    (6,  'Standard',      'TBL-001-S',  799.00),
    (7,  'Standard',      'PAN-001-S',   59.00),
    (8,  'Standard',      'KNF-001-S',  129.00),
    (9,  'Paperback',     'BK-001-P',    45.00),
    (10, 'Paperback',     'BK-002-P',    55.00);

INSERT INTO suppliers (name, contact_email, country) VALUES
    ('Acme Components',   'sales@acme.com',     'USA'),
    ('Global Audio Ltd',  'orders@globalaudio.co.uk', 'UK'),
    ('NordKitchen AB',    'hello@nordkitchen.se',     'Sweden'),
    ('TimberWorks',       'contact@timberworks.ca',   'Canada'),
    ('PaperPress Co',     'sales@paperpress.com',     'USA');

INSERT INTO product_suppliers (product_id, supplier_id, lead_time_days, cost) VALUES
    (1,  1,  10,  850.00),
    (2,  1,  14, 1300.00),
    (3,  2,   7,  180.00),
    (4,  2,   5,   45.00),
    (5,  4,  21,  320.00),
    (6,  4,  28,  450.00),
    (7,  3,  14,   28.00),
    (8,  3,  10,   65.00),
    (9,  5,   3,   18.00),
    (10, 5,   3,   22.00),
    (3,  1,  14,  175.00);  -- StudioPhones also supplied by Acme

INSERT INTO inventory (variant_id, warehouse, quantity) VALUES
    (1,  'NYC-1',   42),
    (2,  'NYC-1',   15),
    (3,  'LA-1',     8),
    (4,  'LA-1',     3),
    (5,  'NYC-1',   60),
    (6,  'NYC-1',   25),
    (7,  'LA-1',  120),
    (8,  'LA-1',   80),
    (9,  'NYC-1',   12),
    (10, 'NYC-1',    7),
    (11, 'CHI-1',  200),
    (12, 'CHI-1',   95),
    (13, 'NYC-1',  300),
    (14, 'NYC-1',  280);

INSERT INTO orders (user_id, address_id, status, total, ordered_at) VALUES
    (1, 1, 'shipped',   1499.00, '2024-09-01 10:15:00'),
    (1, 1, 'delivered',  388.00, '2024-09-12 14:30:00'),
    (2, 2, 'delivered', 1899.00, '2024-09-15 09:00:00'),
    (3, 3, 'pending',    549.00, '2024-10-01 11:45:00'),
    (5, 5, 'shipped',    799.00, '2024-10-05 16:20:00'),
    (6, 6, 'delivered',  188.00, '2024-10-08 12:10:00'),
    (7, 7, 'cancelled',  299.00, '2024-10-10 18:00:00'),
    (1, 1, 'delivered',  100.00, '2024-10-15 08:30:00');

INSERT INTO order_items (order_id, variant_id, quantity, unit_price) VALUES
    (1,  2,  1, 1499.00),
    (2,  5,  1,  299.00),
    (2,  7,  1,   89.00),
    (3,  3,  1, 1899.00),
    (4,  9,  1,  549.00),
    (5, 10,  1,  799.00),
    (6,  8,  1,   89.00),
    (6, 11,  1,   59.00),
    (6, 12,  1,  129.00),  -- intentional small mismatch from total above
    (7,  6,  1,  299.00),
    (8, 13,  1,   45.00),
    (8, 14,  1,   55.00);

INSERT INTO payments (order_id, method, amount, status, paid_at) VALUES
    (1, 'credit_card', 1499.00, 'completed', '2024-09-01 10:16:00'),
    (2, 'paypal',       388.00, 'completed', '2024-09-12 14:31:00'),
    (3, 'credit_card', 1899.00, 'completed', '2024-09-15 09:01:00'),
    (4, 'credit_card',  549.00, 'pending',   NULL),
    (5, 'bank_transfer',799.00, 'completed', '2024-10-05 17:00:00'),
    (6, 'credit_card',  277.00, 'completed', '2024-10-08 12:11:00'),
    (7, 'credit_card',  299.00, 'refunded',  '2024-10-10 18:05:00'),
    (8, 'paypal',       100.00, 'completed', '2024-10-15 08:31:00');

INSERT INTO reviews (user_id, product_id, rating, comment, created_at) VALUES
    (1, 1,  5, 'Fast and light, perfect for travel.',          '2024-09-20'),
    (1, 3,  4, 'Great sound, ear cushions wear quickly.',      '2024-09-25'),
    (2, 2,  5, 'Runs every game on max settings.',             '2024-09-22'),
    (3, 5,  3, 'Comfortable but expensive.',                    '2024-10-12'),
    (5, 6,  5, 'Beautiful desk, sturdy and well finished.',    '2024-10-15'),
    (6, 4,  4, 'Loud and clear, battery life could be better.','2024-10-18'),
    (6, 7,  5, 'Heats evenly, sears beautifully.',             '2024-10-20'),
    (6, 8,  4, 'Sharp out of the box.',                         '2024-10-21'),
    (1, 9,  5, 'Best technical book of the year.',             '2024-10-25'),
    (1, 10, 5, 'A modern classic, highly recommend.',          '2024-10-26');

-- Quick sanity counts
SELECT 'users' AS table, COUNT(*) FROM users UNION ALL
SELECT 'addresses', COUNT(*) FROM addresses UNION ALL
SELECT 'categories', COUNT(*) FROM categories UNION ALL
SELECT 'products', COUNT(*) FROM products UNION ALL
SELECT 'product_variants', COUNT(*) FROM product_variants UNION ALL
SELECT 'suppliers', COUNT(*) FROM suppliers UNION ALL
SELECT 'product_suppliers', COUNT(*) FROM product_suppliers UNION ALL
SELECT 'inventory', COUNT(*) FROM inventory UNION ALL
SELECT 'orders', COUNT(*) FROM orders UNION ALL
SELECT 'order_items', COUNT(*) FROM order_items UNION ALL
SELECT 'payments', COUNT(*) FROM payments UNION ALL
SELECT 'reviews', COUNT(*) FROM reviews;
